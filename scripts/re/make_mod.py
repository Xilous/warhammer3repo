"""Build a tiny WH3 mod pack overriding campaign_variables rows.
usage: python -X utf8 scripts/re/make_mod.py <out.pack> key=value [key=value ...]
Writes a PFH5 'mod' type pack with one db/campaign_variables_tables file. Run from repo root."""
import sys,struct,uuid,os
sys.path.insert(0,'scripts/game'); import packread
def db_campaign_variables(rows):
    g=str(uuid.uuid4()).encode('utf-16-le')
    out=b'\xfd\xfe\xfc\xff'+struct.pack('<H',len(g)//2)+g      # guid marker
    out+=b'\x01'+struct.pack('<I',len(rows))                     # flag byte + row count (version 0: no version marker)
    for k,v in rows:
        kb=k.encode('utf-8'); out+=struct.pack('<H',len(kb))+kb+struct.pack('<f',float(v))
    return out
def write_pack(path,files):
    # files: list of (inner_path_with_backslashes, bytes)
    index=b''.join(struct.pack('<I',len(data))+b'\x00'+name.encode('utf-8')+b'\x00' for name,data in files)
    hdr=b'PFH5'+struct.pack('<6I',3,0,0,len(files),len(index),0)   # type 3 = mod, no timestamps
    with open(path,'wb') as f: f.write(hdr+index+b''.join(d for _,d in files))
if __name__=='__main__':
    out=sys.argv[1]; rows=[kv.split('=',1) for kv in sys.argv[2:]]
    name=os.path.splitext(os.path.basename(out))[0]
    write_pack(out,[('db/campaign_variables_tables/'.replace('/',chr(92))+name, db_campaign_variables(rows))])
    h,ents=packread.read_index(out); print('wrote',out,h,ents)
