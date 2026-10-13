import json
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
base='http://localhost:8081/api/task-workspaces'
here=Path(__file__).parent
id='stage5-identity-runtime-20261008'
def http(path,body=None):
    req=Request(base+path,data=None if body is None else json.dumps(body,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'})
    with urlopen(req,timeout=20) as r:return json.load(r)
receipt=here/'stage5-identity-runtime.json'
if receipt.exists():
    evidence=json.loads(receipt.read_text(encoding='utf-8'))
    current=http('/'+id)
    assert http('/'+id+'/migration-backups/'+evidence['backupId'])==evidence['originalTask']
    assert current['notes']==evidence['identifiedTask']['notes']
else:
    try: original=http('/'+id)
    except HTTPError as error:
        if error.code!=404:raise
        original=http('',{'id':id,'title':'阶段5：旧文档标识补全验收','paperIds':['stage5-test-material.pdf'],
            'notes':[{'content':'标识补全验收正文','versions':[{'text':'验收旧版'}],
                'sources':[{'pdfId':'stage5-test-material.pdf','text':'验收来源字段'}], 'customField':{'retained':True}},
                {'content':'标识补全验收正文'}]})
    result=http('/'+id+'/documents/identify',{'revision':original['revision']})
    assert result['identified']==2
    current=result['task']
    for index,note in enumerate(current['notes']):
        assert {key:value for key,value in note.items() if key!='id'}==original['notes'][index]
    assert current['notes'][0]['id']!=current['notes'][1]['id']
    assert http('/'+id+'/migration-backups/'+result['backupId'])==original
    evidence={'status':'passed','backupId':result['backupId'],'originalTask':original,'identifiedTask':current}
replay=http('/'+id+'/documents/identify',{'revision':current['revision']})
assert replay['identified']==0 and replay['task']==current
evidence['replayNoWrite']=True
receipt.write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':'passed','documents':len(current['notes']),'replayNoWrite':True,'backupExact':True}))
