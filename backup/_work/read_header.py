import sys, struct, re

path = sys.argv[1]
with open(path, 'rb') as f:
    head = f.read(4096)

print("=== HEX DUMP (primeros 256 bytes) ===")
for off in range(0, 256, 16):
    chunk = head[off:off+16]
    hexs = ' '.join(f'{b:02x}' for b in chunk)
    asci = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
    print(f'{off:04x}  {hexs:<47}  {asci}')

print("\n=== STRINGS ASCII (len>=4, primeros 4KB) ===")
for m in re.finditer(rb'[\x20-\x7e]{4,}', head):
    print(f'  {m.start():04x}: {m.group().decode("ascii")}')

print("\n=== STRINGS UTF-16LE (len>=4, primeros 4KB) ===")
for m in re.finditer(rb'(?:[\x20-\x7e]\x00){4,}', head):
    print(f'  {m.start():04x}: {m.group().decode("utf-16-le")}')

print("\n=== CANDIDATOS A VERSION (DWORDs en 0x20-0x60) ===")
for off in range(0x10, 0x80, 4):
    val = struct.unpack_from('<I', head, off)[0]
    if 8 <= val <= 200:
        print(f'  off {off:#04x}: {val}')
