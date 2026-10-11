import sys
from PIL import Image
im=Image.open(sys.argv[1]); h=int(sys.argv[2]) if len(sys.argv)>2 else 1400
W,H=im.size
for i,y in enumerate(range(0,H,h)):
    im.crop((0,y,W,min(H,y+h))).save(f"/tmp/slice_{i}.png")
print(W,H,(H+h-1)//h)
