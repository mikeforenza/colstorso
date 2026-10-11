import sqlite3,sys
c=sqlite3.connect(sys.argv[1] if len(sys.argv)>2 else "data/colstorso.db")
for q in sys.argv[-1].split(";"):
    if q.strip():
        print("--",q.strip()[:80])
        for r in c.execute(q): print(r)
