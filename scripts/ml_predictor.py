#!/usr/bin/env python3
"""ML Price Direction Predictor - Random Forest + Gradient Boosting.

Honesty notes (v3.4.0):
  * models are stored PER SYMBOL — a single shared `ml_model.joblib` used to
    leak one ticker's fitted model into every other ticker's prediction;
  * the scaler is fit on the TRAIN split only (fitting before the split
    leaked test-set statistics and inflated the reported accuracy);
  * the model is chosen on a VALIDATION split, so the TEST accuracy that is
    reported is a genuine out-of-sample number, not a selection artefact;
  * accuracy is reported next to the majority-class baseline, because ~55%
    accuracy on a 55%-up dataset is worthless.
"""
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


def _safe(symbol: str) -> str:
    """Filesystem-safe token for a symbol (US.NVDA -> US_NVDA)."""
    return "".join(c if c.isalnum() else "_" for c in str(symbol))


def model_path_for(symbol: str, model_path: str = None) -> str:
    """Per-symbol model path — never share one model across tickers."""
    if model_path:
        return model_path
    return os.path.join(_SCRIPT_DIR, "..", "data", f"ml_model_{_safe(symbol)}.joblib")


def _save_bundle(path, model, scaler, feature_cols, symbol):
    try:
        import joblib
        os.makedirs(os.path.dirname(path), exist_ok=True)
        joblib.dump({"model": model, "scaler": scaler,
                     "feature_cols": list(feature_cols),
                     "symbol": symbol,
                     "trained_at": datetime.now().isoformat()}, path)
        return path
    except Exception:
        return None


def _majority_baseline(y) -> float:
    """Accuracy of always predicting the most frequent class."""
    if len(y) == 0:
        return 0.0
    y = np.asarray(y)
    counts = np.bincount(y.astype(int))
    return float(counts.max() / counts.sum())


def predict_direction(symbol: str, lookback: int = 60, model_path: str = None) -> Dict:
    """Predict next-bar price direction with an honest out-of-sample estimate."""
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
    X_all_rows = feature_df[feature_cols].values
    y_all = feature_df["target"].values.astype(float)

    # Bars with no genuine forward outcome (NaN target) cannot be trained on,
    # but they are still the rows we most want to PREDICT — keep them in X.
    labeled = ~np.isnan(y_all)
    X = X_all_rows[labeled]
    y = y_all[labeled].astype(int)
    if len(X) < 50:
        result["status"] = "insufficient_features"
        result["error"] = f"only {len(X)} labelled rows (need >= 50)"
        return result

    path = model_path_for(symbol, model_path)

    # 3. Optional explicit model reuse. Only when the caller supplied a path
    #    and the bundle really belongs to this symbol + feature set. A stale
    #    or foreign model is never silently trusted.
    model = None
    scaler = None
    if model_path and os.path.exists(path):
        try:
            import joblib
            saved = joblib.load(path)
            if (saved.get("symbol") == symbol
                    and list(saved.get("feature_cols") or []) == feature_cols):
                model = saved.get("model")
                scaler = saved.get("scaler")
                result["model_source"] = "loaded"
                result["metrics_out_of_sample"] = False
                result["metrics_note"] = ("loaded model - reported accuracy would "
                                          "not be out-of-sample, so it is omitted")
        except Exception:
            model = None

    # 4. Train (always, so the reported metrics are trustworthy)
    if not SKLEARN_OK and model is None:
        result["status"] = "sklearn_unavailable"
        result["error"] = "sklearn not available"
        return result

    if model is None:
        try:
            n = len(X)
            train_end = int(n * 0.6)
            val_end = int(n * 0.8)
            X_train, y_train = X[:train_end], y[:train_end]
            X_val, y_val = X[train_end:val_end], y[train_end:val_end]
            X_test, y_test = X[val_end:], y[val_end:]

            if len(X_val) < 10 or len(X_test) < 10:
                result["status"] = "insufficient_features"
                result["error"] = (f"need >=10 val and >=10 test rows, got "
                                   f"val={len(X_val)} test={len(X_test)}")
                return result

            # Fit the scaler on TRAIN ONLY — fitting on the full matrix leaks
            # test-set mean/variance into training and inflates the score.
            scaler = StandardScaler()
            X_train_s = scaler.fit_transform(X_train)
            X_val_s = scaler.transform(X_val)
            X_test_s = scaler.transform(X_test)

            rf = RandomForestClassifier(
                n_estimators=100, max_depth=8, min_samples_split=5,
                random_state=42, n_jobs=-1, class_weight="balanced"
            )
            gb = GradientBoostingClassifier(
                n_estimators=50, max_depth=4, learning_rate=0.1,
                random_state=42
            )
            rf.fit(X_train_s, y_train)
            gb.fit(X_train_s, y_train)

            # ---- model selection happens on VALIDATION, never on test ----
            rf_val = accuracy_score(y_val, rf.predict(X_val_s))
            gb_val = accuracy_score(y_val, gb.predict(X_val_s))
            if gb_val > rf_val:
                model, result["model_type"] = gb, "GradientBoosting"
                val_acc = gb_val
            else:
                model, result["model_type"] = rf, "RandomForest"
                val_acc = rf_val

            # ---- TEST is touched once, for the number we report ----------
            test_acc = accuracy_score(y_test, model.predict(X_test_s))
            baseline = _majority_baseline(y_test)

            result["model_source"] = "trained_fresh"
            result["metrics_out_of_sample"] = True
            result["train_samples"] = len(X_train)
            result["val_samples"] = len(X_val)
            result["test_samples"] = len(X_test)
            result["val_accuracy"] = round(val_acc, 3)
            result["accuracy"] = round(test_acc, 3)
            result["baseline_accuracy"] = round(baseline, 3)
            result["edge_over_baseline"] = round(test_acc - baseline, 3)
            result["beats_baseline"] = bool(test_acc > baseline)
            result["up_ratio"] = round(float(np.mean(y_train)), 3)

            if hasattr(model, "feature_importances_"):
                importances = model.feature_importances_
                top_indices = np.argsort(importances)[::-1][:10]
                result["top_features"] = [
                    {"name": feature_cols[i], "importance": round(float(importances[i]), 4)}
                    for i in top_indices
                ]

            saved_path = _save_bundle(path, model, scaler, feature_cols, symbol)
            if saved_path:
                result["model_saved"] = saved_path

        except Exception as e:
            result["status"] = "train_error"
            result["error"] = str(e)
            return result

    # 5. Predict the current bar
    try:
        latest_features = feature_df[feature_cols].values[-1:]
        if scaler is not None:
            latest_features = scaler.transform(latest_features)

        prediction = model.predict(latest_features)[0]
        probabilities = model.predict_proba(latest_features)[0]

        confidence = float(max(probabilities))
        direction = "up" if prediction == 1 else "down"

        result["prediction"] = {
            "direction": direction,
            "confidence": round(confidence, 3),
            "prob_up": round(float(probabilities[1]), 3),
            "prob_down": round(float(probabilities[0]), 3),
        }

        # The old "forecast_7d" looked `len - offset` rows BACKWARDS and
        # relabelled past bars as a forecast. Renamed to what it actually is.
        recent = []
        for offset in range(1, 8):
            idx = len(feature_df) - offset
            if idx < 0:
                break
            row = feature_df[feature_cols].values[idx:idx + 1]
            if scaler is not None:
                row = scaler.transform(row)
            prob = model.predict_proba(row)[0]
            recent.append({
                "bars_ago": offset,
                "prob_up": round(float(prob[1]), 3),
                "prob_down": round(float(prob[0]), 3),
            })
        result["recent_bar_signals"] = recent

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
    X_rows = feature_df[feature_cols].values
    y_rows = feature_df["target"].values.astype(float)
    labeled = ~np.isnan(y_rows)
    X_all = X_rows[labeled]
    y_all = y_rows[labeled].astype(int)

    n = len(X_all)
    if n < 100:
        result["status"] = "insufficient_features"
        result["error"] = f"only {n} labelled rows (need >= 100)"
        return result
    train_size = int(n * 0.6)
    val_size = int(n * 0.2)
    test_size = n - train_size - val_size

    if test_size < 20:
        result["status"] = "too_few_samples"
        return result

    X_train, y_train = X_all[:train_size], y_all[:train_size]
    X_val, y_val = X_all[train_size:train_size + val_size], y_all[train_size:train_size + val_size]
    X_test, y_test = X_all[train_size + val_size:], y_all[train_size + val_size:]

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

    val_precision = precision_score(y_val, val_pred, zero_division=0)
    val_recall = recall_score(y_val, val_pred, zero_division=0)
    test_precision = precision_score(y_test, test_pred, zero_division=0)
    test_recall = recall_score(y_test, test_pred, zero_division=0)

    val_trades = int((val_pred == 1).sum())
    val_wins = int(((val_pred == 1) & (y_val == 1)).sum())
    test_trades = int((test_pred == 1).sum())
    test_wins = int(((test_pred == 1) & (y_test == 1)).sum())

    baseline = _majority_baseline(y_test)

    result.update({
        "train_samples": len(X_train),
        "val_samples": len(X_val),
        "test_samples": len(X_test),
        "val_accuracy": round(val_acc, 3),
        "test_accuracy": round(test_acc, 3),
        "baseline_accuracy": round(baseline, 3),
        "edge_over_baseline": round(test_acc - baseline, 3),
        "beats_baseline": bool(test_acc > baseline),
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
