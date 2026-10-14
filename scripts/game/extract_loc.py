"""Extract every English localisation string from the installed game's local_en.pack into tww/loc_en.json.
Run from the repo root. Requires: zstandard (pip install zstandard). Packs are PFH5 with zstd-compressed files."""
import packread,struct,os,zstandard,json
def extract(pk,e):
    with open(os.path.join(packread.GAME,pk),'rb') as f:
        f.seek(e[1]); raw=f.read(e[2])
    if e[3]:
        return zstandard.ZstdDecompressor().decompressobj().decompress(raw[4:])   # u32 uncompressed size, then zstd frame
    return raw
def parse_loc(b):
    assert b[:2]==b'\xff\xfe' and b[2:6]==b'LOC\0', b[:8]
    ver,cnt=struct.unpack_from('<II',b,6); p=14; out={}
    for i in range(cnt):
        l=struct.unpack_from('<H',b,p)[0]; p+=2; k=b[p:p+2*l].decode('utf-16-le'); p+=2*l
        l=struct.unpack_from('<H',b,p)[0]; p+=2; v=b[p:p+2*l].decode('utf-16-le'); p+=2*l
        p+=1   # tooltip flag
        out[k]=v
    return out
if __name__=='__main__':
    pk='local_en.pack'; h,ents=packread.read_index(os.path.join(packread.GAME,pk))
    loc={}
    for e in ents:
        if e[0].endswith('.loc'):
            try: loc.update(parse_loc(extract(pk,e)))
            except Exception as ex: print('ERR',e[0],ex)
    os.makedirs('tww',exist_ok=True)
    json.dump(loc,open('tww/loc_en.json','w',encoding='utf-8'),ensure_ascii=False)
    print('loc entries',len(loc))
