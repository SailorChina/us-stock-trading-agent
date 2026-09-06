import ast

path = chr(115)+chr(99)+chr(114)+chr(105)+chr(112)+chr(116)+chr(115)+chr(47)+chr(109)+chr(97)+chr(114)+chr(107)+chr(101)+chr(116)+chr(95)+chr(115)+chr(101)+chr(110)+chr(116)+chr(105)+chr(109)+chr(101)+chr(110)+chr(46)+chr(112)+chr(121))
with open(path, chr(114)) as f:
    content = f.read()

content = content.replace(chr(105)+chr(109)+chr(112)+chr(111)+chr(114)+chr(116)+chr(32)+chr(106)+chr(115)+chr(111)+chr(110)+chr(44)+chr(32)+chr(115)+chr(121)+chr(115)+chr(44)+chr(32)+chr(97)+chr(114)+chr(103)+chr(112)+chr(97)+chr(114)+chr(115)+chr(44)+chr(32)+chr(116)+chr(105)+chr(109)+chr(101), chr(105)+chr(112)+chr(111)+chr(114)+chr(116)+chr(32)+chr(106)+chr(115)+chr(111)+chr(110)+chr(44)+chr(32)+chr(115)+chr(121)+chr(115)+chr(44)+chr(32)+chr(97)+chr(114)+chr(103)+chr(112)+chr(97)+chr(114)+chr(115)+chr(44)+chr(32)+chr(116)+chr(105)+chr(109)+chr(101)+chr(44)+chr(32)+chr(116)+chr(104)+chr(114)+chr(101)+chr(97)+chr(100)+chr(105)+chr(110)+chr(103)))

print(chr(79)+chr(75))