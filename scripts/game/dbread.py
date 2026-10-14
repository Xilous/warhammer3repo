import packread,struct,os,zstandard,re,json,sys
SCH=json.load(open('rpfm/schemas_sel.json'))
def extract(pk,e):
    with open(os.path.join(packread.GAME,pk),'rb') as f:
        f.seek(e[1]); raw=f.read(e[2])
    if e[3]:
        return zstandard.ZstdDecompressor().decompressobj().decompress(raw[4:])
    return raw
def rd_str8(b,p):
    l=struct.unpack_from('<H',b,p)[0]; p+=2; return b[p:p+l].decode('utf-8','replace'),p+l
def rd_str16(b,p):
    l=struct.unpack_from('<H',b,p)[0]; p+=2; return b[p:p+2*l].decode('utf-16-le','replace'),p+2*l
def parse_db(b,table):
    p=0
    if b[:4]==b'\xfd\xfe\xfc\xff':
        p=4; _,p=rd_str16(b,p)
    ver=0
    if b[p:p+4]==b'\xfc\xfd\xfe\xff':
        ver=struct.unpack_from('<I',b,p+4)[0]; p+=8
    p+=1
    cnt=struct.unpack_from('<I',b,p)[0]; p+=4
    defs=SCH[table]; fields=None
    for v,fl in defs:
        if v==ver: fields=fl
    if fields is None: raise RuntimeError('no schema version %d for %s (have %s)'%(ver,table,[v for v,_ in defs]))
    rows=[]
    for i in range(cnt):
        row={}
        for name,ft in fields:
            if ft=='StringU8': row[name],p=rd_str8(b,p)
            elif ft=='StringU16': row[name],p=rd_str16(b,p)
            elif ft=='OptionalStringU8':
                flag=b[p]; p+=1
                if flag: row[name],p=rd_str8(b,p)
                else: row[name]=''
            elif ft=='OptionalStringU16':
                flag=b[p]; p+=1
                if flag: row[name],p=rd_str16(b,p)
                else: row[name]=''
            elif ft=='Boolean': row[name]=bool(b[p]); p+=1
            elif ft=='F32': row[name]=struct.unpack_from('<f',b,p)[0]; p+=4
            elif ft=='F64': row[name]=struct.unpack_from('<d',b,p)[0]; p+=8
            elif ft=='I16': row[name]=struct.unpack_from('<h',b,p)[0]; p+=2
            elif ft=='I32': row[name]=struct.unpack_from('<i',b,p)[0]; p+=4
            elif ft=='I64': row[name]=struct.unpack_from('<q',b,p)[0]; p+=8
            elif ft=='ColourRGB': row[name]=struct.unpack_from('<I',b,p)[0]; p+=4
            elif ft=='OptionalI32':
                flag=b[p]; p+=1
                if flag: row[name]=struct.unpack_from('<i',b,p)[0]; p+=4
                else: row[name]=None
            else: raise RuntimeError('unhandled type '+ft)
        rows.append(row)
    return rows
def load_table(table,packs=('db.pack','data.pack','data_3.pack')):
    rows=[]
    for pk in packs:
        try: h,ents=packread.read_index(os.path.join(packread.GAME,pk))
        except Exception as ex: print('skip',pk,ex); continue
        for e in ents:
            n=e[0].replace('\\','/')
            if n.startswith('db/'+table+'/'):
                try:
                    r=parse_db(extract(pk,e),table); rows+=r
                except Exception as ex: print('ERR',pk,e[0],ex)
    return rows
if __name__=='__main__':
    for t in sys.argv[1:]:
        r=load_table(t); print(t,len(r)); print(r[:3])
