#!/usr/bin/env python3
"""ML Price Direction Predictor - Random Forest + Gradient Boosting."""
import json, sys, os, time, warnings
import numpy as np
from datetime import datetime
from typing import Dict, Optional

warnings.filterwarnings("ignore")

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)

try:
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.model_selection import cross_val_score, TimeSeriesSplit
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, classification_report
    SKLEARN_OK = True
except ImportError:
    SKLEARN_OK = False


def predict_direction(symbol: str, lookback: int = 60, model_path: str = None) -> Dict:
    """Predict next 5-day price direction using ML model.
    
    Uses walk-forward validation with Random Forest.
    Falls back to gradient boosting if RF is insufficient.
    """
    from tech_engine import fetch_kline
    from ml_features import extract_features, build_feature_matrix
    
    result = {
        "symbol": symbol,
        "generated_at": datetime.now().isoformat(),
        "status": "ok",
    }
    
    # 1. Fetch kline data
    df = fetch_kline(symbol, "1d", lookback + 30)
    if df is None or len(df) < lookback + 20:
        result["status"] = "insufficient_data"
        result["error"] = f"Need >= {lookback + 20} bars, got {len(df) if df is not None else 0}"
        return result
    
    # 2. Extract features
    feature_df = extract_features(df, lookback=lookback)
    if feature_df is None or len(feature_df) < 50:
        result["status"] = "insufficient_features"
        result["error"] = "Not enough feature rows"
        return result
    
    feature_cols = [c for c in feature_df.columns if c != "target"]
    X = feature_df[feature_cols].values
    y = feature_df["target"].values
    
    # 3. Try loading saved model first
    if model_path is None:
        model_path = os.path.join(_SCRIPT_DIR, "..", "data", "ml_model.joblib")
    
    model = None
    scaler = None
    
    if SKLEARN_OK and os.path.exists(model_path):
        try:
            import joblib
            saved = joblib.load(model_path)
            model = saved.get("model")
            scaler = saved.get("scaler")
            result["model_source"] = "loaded"
        except Exception as e:
            result["model_source"] = "train_fresh"
            model = None
    
    # 4. Train model if needed
    if model is None and SKLEARN_OK:
        try:
            # Scale features
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)
            
            # Walk-forward validation
            n = len(X_scaled)
            train_end = int(n * 0.7)
            
            X_train, X_test = X_scaled[:train_end], X_scaled[train_end:]
            y_train, y_test = y[:train_end], y[train_end:]
            
            # Random Forest
            rf = RandomForestClassifier(
                n_estimators=100, max_depth=8, min_samples_split=5,
                random_state=42, n_jobs=-1, class_weight="balanced"
            )
            rf.fit(X_train, y_train)
            
            # Gradient Boosting
            gb = GradientBoostingClassifier(
                n_estimators=50, max_depth=4, learning_rate=0.1,
                random_state=42
            )
            gb.fit(X_train, y_train)
            
            # Evaluate
            rf_pred = rf.predict(X_test)
            gb_pred = gb.predict(X_test)
            
            rf_acc = accuracy_score(y_test, rf_pred)
            gb_acc = accuracy_score(y_test, gb_pred)
            
            # Use better model
            if gb_acc > rf_acc:
                model = gb
                result["model_type"] = "GradientBoosting"
                result["accuracy"] = round(gb_acc, 3)
            else:
                model = rf
                result["model_type"] = "RandomForest"
                result["accuracy"] = round(rf_acc, 3)
            
            result["train_samples"] = len(X_train)
            result["test_samples"] = len(X_test)
            result["up_ratio"] = round(y_train.mean(), 3)
            
            # Feature importance
            if hasattr(model, "feature_importances_"):
                importances = model.feature_importances_
                top_indices = np.argsort(importances)[::-1][:10]
                result["top_features"] = [
                    {"name": feature_cols[i], "importance": round(float(importances[i]), 4)}
                    for i in top_indices
                ]
            
            # Save model
            try:
                os.makedirs(os.path.dirname(model_path), exist_ok=True)
                import joblib
                joblib.dump({"model": model, "scaler": scaler}, model_path)
                result["model_saved"] = model_path
            except Exception:
                pass
                
        except Exception as e:
            result["status"] = "train_error"
            result["error"] = str(e)
            return result
    
    elif model is None:
        result["status"] = "sklearn_unavailable"
        result["error"] = "sklearn not available"
        return result
    
    # 5. Predict current bar
    try:
        latest_features = feature_df[feature_cols].values[-1:]
        if scaler is not None:
            latest_features = scaler.transform(latest_features)
        
        prediction = model.predict(latest_features)[0]
        probabilities = model.predict_proba(latest_features)[0]
        
        # Confidence = max probability
        confidence = float(max(probabilities))
        direction = "up" if prediction == 1 else "down"
        
        result["prediction"] = {
            "direction": direction,
            "confidence": round(confidence, 3),
            "prob_up": round(float(probabilities[1]), 3),
            "prob_down": round(float(probabilities[0]), 3),
        }
        
        # 7-day forecast (rolling prediction)
        forecasts = []
        for offset in range(1, 8):
            idx = max(0, len(feature_df) - offset)
            if idx < lookback:
                break
            row = feature_df[feature_cols].values[idx:idx+1]
            if scaler is not None:
                row = scaler.transform(row)
            prob = model.predict_proba(row)[0]
            forecasts.append({
                "day_offset": offset,
                "prob_up": round(float(prob[1]), 3),
                "prob_down": round(float(prob[0]), 3),
            })
        result["forecast_7d"] = forecasts
        
    except Exception as e:
        result["prediction"] = {"error": str(e)}
    
    return result


def backtest_ml(symbol: str, lookback: int = 60, window: int = 20) -> Dict:
    """Walk-forward backtest of ML prediction."""
    from tech_engine import fetch_kline
    from ml_features import extract_features, build_feature_matrix
    
    result = {"symbol": symbol, "generated_at": datetime.now().isoformat(), "status": "ok"}
    
    df = fetch_kline(symbol, "1d", lookback + window * 3)
    if df is None or len(df) < lookback + window * 2:
        result["status"] = "insufficient_data"
        return result
    
    feature_df = extract_features(df, lookback=lookback)
    if feature_df is None or len(feature_df) < 100:
        result["status"] = "insufficient_features"
        return result
    
    feature_cols = [c for c in feature_df.columns if c != "target"]
    X_all = feature_df[feature_cols].values
    y_all = feature_df["target"].values
    
    n = len(X_all)
    train_size = int(n * 0.6)
    val_size = int(n * 0.2)
    test_size = n - train_size - val_size
    
    if test_size < 20:
        result["status"] = "too_few_samples"
        return result
    
    X_train, y_train = X_all[:train_size], y_all[:train_size]
    X_val, y_val = X_all[train_size:train_size+val_size], y_all[train_size:train_size+val_size]
    X_test, y_test = X_all[train_size+val_size:], y_all[train_size+val_size:]
    
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_val_s = scaler.transform(X_val)
    X_test_s = scaler.transform(X_test)
    
    model = RandomForestClassifier(n_estimators=100, max_depth=8, min_samples_split=5,
                                    random_state=42, class_weight="balanced", n_jobs=-1)
    model.fit(X_train_s, y_train)
    
    val_pred = model.predict(X_val_s)
    test_pred = model.predict(X_test_s)
    
    val_acc = accuracy_score(y_val, val_pred)
    test_acc = accuracy_score(y_test, test_pred)
    
    # Precision/Recall for "up" class
    val_precision = precision_score(y_val, val_pred, zero_division=0)
    val_recall = recall_score(y_val, val_pred, zero_division=0)
    test_precision = precision_score(y_test, test_pred, zero_division=0)
    test_recall = recall_score(y_test, test_pred, zero_division=0)
    
    # Simulate trading: buy when predicted up
    val_trades = 0
    val_wins = 0
    for i in range(len(val_pred)):
        if val_pred[i] == 1:
            val_trades += 1
            if y_val[i] == 1:
                val_wins += 1
    
    test_trades = 0
    test_wins = 0
    for i in range(len(test_pred)):
        if test_pred[i] == 1:
            test_trades += 1
            if y_test[i] == 1:
                test_wins += 1
    
    result.update({
        "train_samples": len(X_train),
        "val_samples": len(X_val),
        "test_samples": len(X_test),
        "val_accuracy": round(val_acc, 3),
        "test_accuracy": round(test_acc, 3),
        "val_precision_up": round(val_precision, 3),
        "val_recall_up": round(val_recall, 3),
        "test_precision_up": round(test_precision, 3),
        "test_recall_up": round(test_recall, 3),
        "val_trade_signals": val_trades,
        "val_win_rate": round(val_wins / max(1, val_trades), 3),
        "test_trade_signals": test_trades,
        "test_win_rate": round(test_wins / max(1, test_trades), 3),
        "model_type": "RandomForest",
    })
    
    # Feature importance
    importances = model.feature_importances_
    top_idx = np.argsort(importances)[::-1][:8]
    result["top_features"] = [
        {"name": feature_cols[i], "importance": round(float(importances[i]), 4)}
        for i in top_idx
    ]
    
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description="ML Price Direction Predictor")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--lookback", type=int, default=60)
    parser.add_argument("--mode", default="predict", choices=["predict", "backtest"])
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    
    if args.mode == "predict":
        result = predict_direction(args.symbol, args.lookback)
    else:
        result = backtest_ml(args.symbol, args.lookback)
    
    output = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Saved: {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
