from fastapi.testclient import TestClient
from colstorso.main import app
import traceback
c=TestClient(app, raise_server_exceptions=False)
H=lambda u:{"X-User":str(u)}
for u,path in [(1,"/api/meta"),(11,"/api/home"),(5,"/api/home"),(5,"/api/team"),(1,"/api/business"),(11,"/api/business"),(1,"/api/kpi/labor"),(11,"/api/kpi/total_sales"),(11,"/api/pnl"),(1,"/api/pnl?mode=biggest"),(1,"/api/impact"),(5,"/api/visits/suggest"),(5,"/api/visits"),(1,"/api/campaigns"),(1,"/api/ai/themes"),(1,"/api/tasks/analytics"),(1,"/api/dc"),(1,"/api/data/uploads"),(1,"/api/comms"),(11,"/api/comms"),(1,"/api/bestpractices"),(1,"/api/surveys"),(1,"/api/task_templates"),(1,"/api/task_rules"),(1,"/api/mission_rules"),(1,"/api/admin/permissions"),(1,"/api/admin/users"),(1,"/api/admin/stores"),(11,"/api/countlist?store=1"),(11,"/api/tasks"),(1,"/api/ai/context"),(1,"/api/capacity"),(1,"/api/blackouts"),(1,"/api/export/missions.csv"),(1,"/embed/store/S001")]:
    r=c.get(path,headers=H(u)); print(u,path,r.status_code, r.text[:110].replace("\n"," "))
m=c.get("/api/missions?status=incoming",headers=H(11)).json(); print("incoming S001", len(m), [x["label"] for x in m], [x["confidence"] for x in m])
print(c.get(f"/api/missions/{m[0]['id']}/plan",headers=H(11)).json())
r=c.post(f"/api/missions/{m[0]['id']}/quick",json={"action":"accept"},headers=H(11)); print("quick accept",r.status_code,r.json().get("label"), r.json().get("control_ids"))
if len(m)>1: print("snooze", c.post(f"/api/missions/{m[1]['id']}/quick",json={"action":"snooze"},headers=H(11)).json()["label"])
if len(m)>2: print("nfu", c.post(f"/api/missions/{m[2]['id']}/quick",json={"action":"not_for_us"},headers=H(11)).json()["label"])
print("pushback", str(c.get("/api/pushback",headers=H(1)).json())[:300])
print("fresh", c.get("/api/freshness",headers=H(1)).json())
lv=c.get("/api/missions?status=live,done",headers=H(1)).json(); print("impact sample", [(x["impact"]["cumulative"],x["impact"]["low"],x["impact"]["high"],x["impact"]["confidence"]) for x in lv[:6]])
print("must campaign over limit:", c.post("/api/campaigns",json={"name":"X1","push":"must","kpis":["labor"]},headers=H(1)).status_code)
print(c.post("/api/campaigns/preview",json={"target":{"formats":["Standard"]},"kpis":["labor"]},headers=H(1)).json())
print(c.post("/api/ai/ask",json={"q":"What worked for Fresh waste?"},headers=H(11)).json())
