"""Import/replace local photos as bounded metadata-free RGB565 viewing frames."""
import argparse,hashlib,json,re,sys
from pathlib import Path
import numpy as np
from PIL import Image,ImageOps
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from eye_tracker.album import PhotoLibrary,PHOTO_SHAPE,MAX_PHOTOS
from eye_tracker.framebuffer import pack_rgb565


def import_photo(source,key,title,root=ROOT,replace=False,credit=None):
    folder=Path(root)/'assets/photos';folder.mkdir(parents=True,exist_ok=True)
    manifest=folder/'album.json'
    if not manifest.exists():manifest.write_text('{"version":1,"photos":[]}\n',encoding='utf-8')
    lib=PhotoLibrary(folder)
    if not re.fullmatch('[a-z0-9][a-z0-9_-]{0,39}',key) or not isinstance(title,str) or not 1<=len(title)<=20 or any(ord(c)<32 for c in title):
        raise ValueError('invalid photo id/title')
    matches=[i for i,x in enumerate(lib.photos) if x['id']==key]
    if matches and not replace:raise ValueError('photo exists; replacement must be explicit')
    if not matches and len(lib.photos)>=MAX_PHOTOS:raise ValueError('album full')
    with Image.open(source) as opened:
        if opened.width*opened.height>25000000 or opened.width>12000 or opened.height>12000:raise ValueError('source image too large')
        if getattr(opened,'n_frames',1)!=1:raise ValueError('animated images are not photos')
        picture=ImageOps.exif_transpose(opened).convert('RGB')
        fitted=ImageOps.contain(picture,(PHOTO_SHAPE[1],PHOTO_SHAPE[0]),getattr(Image,'Resampling',Image).LANCZOS)
    canvas=Image.new('RGB',(PHOTO_SHAPE[1],PHOTO_SHAPE[0]),'#142D31')
    canvas.paste(fitted,((canvas.width-fitted.width)//2,(canvas.height-fitted.height)//2))
    raw=pack_rgb565(np.asarray(canvas)).astype('<u2').tobytes()
    item=dict(id=key,title=title,file=key+'.rgb565',sha256=hashlib.sha256(raw).hexdigest(),credit=credit or {'source':'user-provided local image'})
    items=list(lib.photos)
    if matches:items[matches[0]]=item
    else:items.append(item)
    target=folder/item['file'];pending=target.with_suffix('.pending')
    staged=manifest.with_suffix('.json.pending')
    old=target.read_bytes() if target.exists() else None
    try:
        pending.write_bytes(raw)
        staged.write_text(json.dumps({'version':1,'photos':items},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        pending.replace(target)
        try:staged.replace(manifest)
        except OSError:
            if old is None:target.unlink()
            else:target.write_bytes(old)
            raise
    finally:
        for p in (pending,staged):
            if p.exists():p.unlink()
    return item


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path);parser.add_argument('--id',required=True);parser.add_argument('--title',required=True)
    parser.add_argument('--replace',action='store_true')
    a=parser.parse_args();print(json.dumps(import_photo(a.source,a.id,a.title,replace=a.replace),ensure_ascii=False))
    print('Rebuild text assets to include the photo title, then package while the board is idle.')
