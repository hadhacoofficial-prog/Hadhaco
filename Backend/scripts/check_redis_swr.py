"""Quick Redis SWR structure check."""
import sys, json, zlib, time
sys.stdout.reconfigure(encoding='utf-8')

import redis
r = redis.Redis(host='localhost', port=6379, decode_responses=True)

print("=== ALL REDIS KEYS ===\n")
for key in sorted(r.keys("*")):
    val = r.get(key)
    ttl = r.ttl(key)
    is_compressed = val and len(val) > 0 and val[0] == chr(1)
    
    try:
        if is_compressed:
            decompressed = zlib.decompress(val[1:].encode('latin-1')).decode('utf-8')
            data = json.loads(decompressed) if decompressed else {}
            orig_size = len(decompressed)
        elif val:
            data = json.loads(val)
            orig_size = len(val)
        else:
            data = {}
            orig_size = 0
    except Exception:
        data = {}
        orig_size = len(val) if val else 0
    
    has_swr = isinstance(data, dict) and 'd' in data and 't' in data
    age = time.time() - data.get('t', 0) if has_swr else -1
    
    d = data.get('d', data) if has_swr else data
    extra = ""
    if isinstance(d, dict):
        if 'items' in d:
            extra = f"items={len(d['items'])}"
        elif 'total' in d:
            extra = f"total={d['total']}"
    
    print(f"  {key:40s} TTL={ttl:>6d}s  size={orig_size:>7,d}B  compressed={is_compressed}  swr={has_swr}  age={age:>6.0f}s  {extra}")

print("\n=== COMPRESSION ANALYSIS ===\n")
for key in sorted(r.keys("*")):
    val = r.get(key)
    if not val:
        print(f"  {key:40s} (empty)")
        continue
    is_compressed = val[0] == chr(1)
    if is_compressed:
        try:
            decompressed = zlib.decompress(val[1:].encode('latin-1')).decode('utf-8')
            decomp_size = len(decompressed)
            ratio = decomp_size / len(val) if len(val) > 0 else 0
            print(f"  {key:40s} compressed={len(val):>6,d}B  decompressed={decomp_size:>7,d}B  ratio={ratio:.1f}x")
        except Exception as e:
            print(f"  {key:40s} compressed (corrupt?): {e}")
    else:
        print(f"  {key:40s} uncompressed={len(val):>6,d}B")
