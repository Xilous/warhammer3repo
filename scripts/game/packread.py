import struct,sys,os,json
GAME=r"C:\Program Files (x86)\Steam\steamapps\common\Total War WARHAMMER III\data"
def read_header(f):
    f.seek(0)
    magic=f.read(4)
    bitmask,pack_count,pack_index_size,file_count,file_index_size,timestamp=struct.unpack('<6I',f.read(24))
    hdr=28
    if magic==b'PFH6':
        hdr+=4+256  # game version + build string
    elif magic==b'PFH5':
        pass
    else:
        raise SystemExit('unknown magic %r'%magic)
    return dict(magic=magic.decode(),bitmask=bitmask,pack_count=pack_count,pack_index_size=pack_index_size,file_count=file_count,file_index_size=file_index_size,hdr=hdr)
def read_index(path):
    f=open(path,'rb'); h=read_header(f)
    f.seek(h['hdr'])
    pack_index=f.read(h['pack_index_size'])
    idx=f.read(h['file_index_size'])
    has_ts=bool(h['bitmask']&0x40)
    entries=[]; p=0; n=0
    data_start=h['hdr']+h['pack_index_size']+h['file_index_size']
    off=data_start
    while n<h['file_count']:
        size=struct.unpack_from('<I',idx,p)[0]; p+=4
        ts=0
        if has_ts: ts=struct.unpack_from('<I',idx,p)[0]; p+=4
        comp=idx[p]; p+=1
        e=idx.index(b'\0',p); name=idx[p:e].decode('utf-8','replace'); p=e+1
        entries.append((name,off,size,comp)); off+=size; n+=1
    f.close()
    return h,entries
def extract(path,entry):
    name,off,size,comp=entry
    with open(path,'rb') as f:
        f.seek(off); data=f.read(size)
    if comp:
        # WH3 compressed packed files: u32 uncompressed size + lz4 magic (04 22 4D 18) frame? or raw block
        try:
            import lz4.frame, lz4.block
            usize=struct.unpack_from('<I',data,0)[0]
            try:
                return lz4.frame.decompress(data[4:])
            except Exception:
                return lz4.block.decompress(data[4:],uncompressed_size=usize)
        except ImportError:
            raise RuntimeError('compressed file %s but lz4 module missing'%name)
    return data
if __name__=='__main__':
    for pk in sys.argv[1:]:
        h,ents=read_index(os.path.join(GAME,pk))
        print(pk,h,'entries',len(ents),'compressed',sum(1 for e in ents if e[3]))
        for e in ents:
            n=e[0].lower()
            if any(s in n for s in ['db/technolog','db/character_skill','db/effect','db/unit_set','.loc','db/unit_sets','db/technologies']):
                if 'db/' in n or n.endswith('.loc'):
                    print('  ',e[0],e[2],'C' if e[3] else '')
