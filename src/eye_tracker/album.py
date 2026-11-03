"""Bounded local RGB565 photo library, one decoded frame cached at a time."""
import hashlib,json,re
from pathlib import Path
import numpy as np

PHOTO_BOX=(16,112,624,408)
PHOTO_SHAPE=(296,608)
PHOTO_BYTES=296*608*2
MAX_PHOTOS=32


class PhotoLibrary:
    def __init__(self,folder):
        self.folder=Path(folder).resolve();p=self.folder/'album.json'
        if p.stat().st_size>65536:raise ValueError('album manifest too large')
        data=json.loads(p.read_text(encoding='utf-8'))
        if not isinstance(data,dict):raise ValueError('invalid album manifest')
        if type(data.get('version')) is not int or data['version']!=1 or not isinstance(data.get('photos'),list):
            raise ValueError('invalid album manifest')
        if len(data['photos'])>MAX_PHOTOS:raise ValueError('album full')
        self.photos=[];ids=set()
        for item in data['photos']:
            if not isinstance(item,dict):raise ValueError('invalid photo entry')
            key=item.get('id');title=item.get('title');name=item.get('file')
            if (not isinstance(key,str) or not re.fullmatch('[a-z0-9][a-z0-9_-]{0,39}',key) or key in ids or
                not isinstance(title,str) or not 1<=len(title)<=20 or any(ord(c)<32 for c in title) or
                name!=key+'.rgb565' or not re.fullmatch('[0-9a-f]{64}',str(item.get('sha256')))):
                raise ValueError('invalid photo entry')
            path=(self.folder/name).resolve();path.relative_to(self.folder)
            if path.stat().st_size!=PHOTO_BYTES or hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:
                raise ValueError('photo pixels/hash mismatch')
            ids.add(key);self.photos.append(dict(item))
        self._index=None;self._pixels=None

    def frame(self,index):
        if type(index) is not int or not 0<=index<len(self.photos):raise ValueError('invalid photo index')
        if index!=self._index:
            item=self.photos[index];raw=(self.folder/item['file']).read_bytes()
            if len(raw)!=PHOTO_BYTES or hashlib.sha256(raw).hexdigest()!=item['sha256']:
                raise ValueError('photo changed after preflight')
            self._pixels=np.frombuffer(raw,dtype='<u2').reshape(PHOTO_SHAPE)
            self._index=index
        return self._pixels

    def provenance(self):return [dict(x) for x in self.photos]
