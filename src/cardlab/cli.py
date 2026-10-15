import argparse
from collections import Counter
from datetime import datetime,timezone
import hashlib,json,os,random,re,sys,tempfile,zipfile
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from . import engine as e

REPO=Path(__file__).resolve().parents[2]
PUBLIC=e.PUBLIC_FIELDS
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def jsonl(p):return [json.loads(x) for x in Path(p).read_text(encoding='utf-8-sig').splitlines() if x.strip()]
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def output(p,x):e.save(Path(p),x)
def records(label):
    folder=REPO/'data'/label
    stories=jsonl(folder/'stories.jsonl')
    lookup={arm:{x['id']:x for x in jsonl(folder/f'predictions-{arm.replace("_","-")}.jsonl')} for arm in ['cards','no_cards']}
    assert len({s['id'] for s in stories})==len(stories)
    for arm in lookup:assert set(lookup[arm])=={s['id'] for s in stories}
    return [dict(s,cards_prediction=lookup['cards'][s['id']],no_cards_prediction=lookup['no_cards'][s['id']]) for s in stories]
def verify_package():
    manifest=read(REPO/'manifest.json')
    for name,sha in manifest['files'].items():
        p=REPO/name
        if not p.is_file() or digest(p)!=sha:raise ValueError('Package file changed/missing: '+name)
    rounds=jsonl(REPO/'data/exploration/rounds.jsonl')
    assert len(rounds)==834
    assert dict(Counter(x['phase'] for x in rounds))=={'phase1':468,'pretest':6,'phase2':360}
    selection=read(REPO/'teaching/selection.json')
    full={r['id']:r for r in records('evaluation-1000')}
    assert len(selection['case_ids'])==len(set(selection['case_ids']))==40
    assert all(full[i]['cards_prediction']['prediction']==full[i]['outcome'] for i in selection['case_ids'])
    return {'package_files':len(manifest['files']),'exploration_rounds':834,'teaching_cases':40,'hashes':'pass'}
def safe_extract(z,target):
    target=Path(target).resolve()
    for item in z.infolist():
        resolved=(target/item.filename).resolve()
        if not resolved.is_relative_to(target) or '\\' in item.filename:raise ValueError('Unsafe archive member')
    z.extractall(target)
def reproduce(out):
    out=Path(out)
    if out.exists() and any(out.iterdir()):raise ValueError('Output directory must be empty')
    verification=verify_package()
    pilot=records('pilot-100');large=records('evaluation-1000')
    result={'pilot_all':e.comparison(pilot),'pilot_holdout':e.comparison([r for r in pilot if r['split']=='holdout']),
            'evaluation_1000':e.comparison(large)}
    assert result['pilot_all']['cards']['correct']==65 and result['pilot_all']['no_cards']['correct']==69
    assert result['pilot_holdout']['cards']['correct']==26 and result['pilot_holdout']['no_cards']['correct']==29
    s=result['evaluation_1000']
    assert (s['cards']['correct'],s['no_cards']['correct'],s['both_correct'],s['both_wrong'],s['cards_only_correct'],s['no_cards_only_correct'])==(704,691,651,256,53,40)
    draws={x['id']:x for x in jsonl(REPO/'data/evaluation-1000/draws.jsonl')}
    for r in large:
        cards=r['cards_prediction']['cards']
        assert len(cards)==len(set(cards))==3 and set(cards)<=set(e.DECK)
        assert cards==draws[r['id']]['cards']
    # Verify the historical submissions with their ORIGINAL manifests, not a newly computed replacement.
    out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='cardlab_archive_',dir=out) as tmp:
        with zipfile.ZipFile(REPO/'archive/evaluation-1000-frozen.zip') as z:
            assert z.testzip() is None
            safe_extract(z,tmp)
        archive_check=e.verify(Path(tmp))
        assert archive_check['count']==1000 and not archive_check['fixture']
        original=read(Path(tmp)/'results.json')
        assert s==e.comparison(original['rows'])
    result['verification']=dict(verification,historical_freeze='pass',draws='pass')
    output(out/'summary.json',result)
    text=['# 重算结果','', '| 数据集 | 有牌 | 无牌 |','|---|---:|---:|']
    for title,key in [('百例全部','pilot_all'),('百例留出','pilot_holdout'),('千例','evaluation_1000')]:
        v=result[key];text.append(f"| {title} | {v['cards']['correct']}/{v['cards']['n']} | {v['no_cards']['correct']}/{v['no_cards']['n']} |")
    text+=['',f"千例配对精确检验 p={s['mcnemar_exact_two_sided']:.6f}。",'', '原始文件哈希、封存记录、牌序和40例教学选例检查通过。']
    (out/'report.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
    return result
def demo(root):
    root=Path(root)
    if root.exists():raise ValueError('Demo target must not exist')
    root.mkdir(parents=True)
    stories=[dict(id=f'F{i+1:03}',domain='tool-fixture',background=f'工具演示场景{i+1}，不属于研究样本。',question='工具测试结果是否为1？',deadline='fixture',
        yes_definition='标签等于1',outcome=i%2,ending=f'演示标签{i%2}',source_type='simulated',source={'reference':'offline tool fixture','evidence':'synthetic known label'}) for i in range(4)]
    output(root/'fixture-stories.json',stories)
    run=root/'run'
    e.initialize(run,root/'fixture-stories.json',REPO/'methods/evaluation-2.0-frozen',fixture=True,count=4,batch_size=2,seed=42)
    e.prepare(run)
    for arm,preds in [('cards',[0,1,1,0]),('no_cards',[0,0,0,1])]:
        forecast=[]
        for i,row in enumerate(e.expected_rows(run,arm).values()):
            pred=preds[i];p=dict(id=row['id'],prediction=pred,p_yes=.8 if pred else .2,answer='工具演示专用回答')
            if arm=='cards':p.update(version='2.0',cards=row['cards'],translations=[dict(card=c,suit_meaning='fixture',value_meaning='fixture',context_translation='fixture') for c in row['cards']],combined_sentence='工具测试固定输出')
            else:p['rationale']='工具测试固定对照'
            forecast.append(p)
        path=root/f'fixture-{arm}.json';output(path,forecast);e.submit(run,arm,path)
    e.seal(run)
    audit=root/'fixture-audit.json';output(audit,[dict(id=s['id'],status='pass',reason='fixture label checked') for s in stories])
    e.submit_audit(run,audit);summary=e.score(run);e.verify(run)
    assert summary['cards']['correct']==2 and summary['no_cards']['correct']==3
    return {'fixture_only':True,'external_calls':0,'summary':summary}

def model_call(config,role,system,user):
    cfg=read(config);settings=dict(cfg['provider']);settings.update(cfg.get('roles',{}).get(role,{}))
    endpoint=settings['endpoint'];parsed=urlparse(endpoint)
    if parsed.scheme!='https' and not (parsed.scheme=='http' and parsed.hostname in ['127.0.0.1','localhost']):raise ValueError('Use HTTPS or localhost test endpoint')
    key=os.environ.get(settings.get('api_key_env','MODEL_API_KEY'),'')
    payload={'model':settings['model'],'messages':[{'role':'system','content':system},{'role':'user','content':user}],
             'temperature':settings.get('temperature',0.2),'max_tokens':settings.get('max_tokens',6000)}
    headers={'Content-Type':'application/json'}
    if key:headers['Authorization']='Bearer '+key
    request=Request(endpoint,data=json.dumps(payload,ensure_ascii=False).encode(),headers=headers,method='POST')
    try:
        with urlopen(request,timeout=settings.get('timeout',45)) as response:raw=json.load(response)
    except HTTPError as exc:raise ValueError(f'Model endpoint returned HTTP {exc.code}') from None
    content=raw['choices'][0]['message']['content']
    content=re.sub(r'^```(?:json)?\s*|\s*```$','',content.strip())
    value=json.loads(content)
    metadata={'role':role,'requested_model':settings['model'],'returned_model':raw.get('model'),'temperature':payload['temperature'],
        'max_tokens':payload['max_tokens'],'created_at':datetime.now(timezone.utc).isoformat(),
        'prompt_sha256':hashlib.sha256((system+'\n'+user).encode()).hexdigest(),'response_content_sha256':hashlib.sha256(content.encode()).hexdigest()}
    return value,metadata
def generate(args):
    if args.count<=0 or not 1<=args.batch_size<=20:raise ValueError('Positive count; batch size 1..20')
    target=Path(args.output)
    if target.exists():raise ValueError('Generation output already exists')
    prompt=(REPO/'prompts/new-experiment/author.md').read_text(encoding='utf-8')
    stories=[];calls=[]
    for start in range(0,args.count,args.batch_size):
        count=min(args.batch_size,args.count-start)
        request={'count':count,'starting_id':start+1,'topic_hint':args.topic,'earlier_backgrounds':[r['background'] for r in stories[-20:]]}
        reply,meta=model_call(args.config,'author',prompt,json.dumps(request,ensure_ascii=False));calls.append(meta)
        if not isinstance(reply,list) or len(reply)!=count:raise ValueError('Author must return exact requested array length')
        for i,s in enumerate(reply,start+1):
            s['id']=f'N{i:04}';s['source_type']='simulated';s['source']={'reference':'new model-authored story','evidence':s.get('ending','')}
            stories.append(s)
        e.validate_stories(stories,len(stories))
    output(target,stories);output(target.with_suffix('.metadata.json'),{'new_template':True,'calls':calls})
    return {'generated':len(stories),'output':str(target)}
def predict(args):
    run=Path(args.root);e.validate_init(run)
    # Only read the public packet. No outcomes, private stories, or other arm's submissions are loaded.
    packet=Path(args.packet)
    expected_folder=(run/'packets'/args.arm).resolve()
    if not packet.resolve().is_relative_to(expected_folder):raise ValueError('Packet must be in the chosen arm packet directory')
    expected=e.expected_rows(run,args.arm)
    batch=read(packet)
    for row in batch:
        if row!=expected.get(row['id']):raise ValueError('Packet differs from frozen public input')
    system=(REPO/'prompts/new-experiment'/f'{args.arm}.md').read_text(encoding='utf-8')
    if args.arm=='cards':
        system+='\n\n'+(run/'method/SKILL.md').read_text(encoding='utf-8')+'\n\n'+(run/'method/references/symbols.md').read_text(encoding='utf-8')
    reply,metadata=model_call(args.config,args.arm,system,json.dumps(batch,ensure_ascii=False))
    if not isinstance(reply,list) or len(reply)!=len(batch):raise ValueError('Predictor must return one object per item')
    if {r.get('id') for r in reply}!={r['id'] for r in batch}:raise ValueError('Prediction IDs mismatch')
    for row in reply:e.validate_prediction(row,expected,args.arm)
    output(args.output,reply);output(Path(args.output).with_suffix('.metadata.json'),metadata)
    return {'predictions':len(reply),'arm':args.arm,'output':args.output,'submitted':False}

def parser():
    p=argparse.ArgumentParser(description='Three-card language experiment tools (standard library only)')
    sub=p.add_subparsers(dest='action',required=True)
    sub.add_parser('verify-package')
    q=sub.add_parser('reproduce');q.add_argument('--output',default='runs/reproduced')
    q=sub.add_parser('demo');q.add_argument('--root',default='runs/offline-demo')
    q=sub.add_parser('generate');q.add_argument('--config',required=True);q.add_argument('--count',type=int,default=10);q.add_argument('--batch-size',type=int,default=5);q.add_argument('--output',required=True);q.add_argument('--topic',default='日常生活中的协作、使用、交付与选择')
    q=sub.add_parser('predict');q.add_argument('--root',required=True);q.add_argument('--packet',required=True);q.add_argument('--arm',choices=['cards','no_cards'],required=True);q.add_argument('--config',required=True);q.add_argument('--output',required=True)
    for action in ['init','prepare','submit','seal','audit','score','verify']:
        q=sub.add_parser(action);q.add_argument('--root',required=True)
        if action=='init':
            q.add_argument('--stories',required=True);q.add_argument('--method',default=str(REPO/'methods/evaluation-2.0-frozen'));q.add_argument('--count',type=int,required=True);q.add_argument('--batch-size',type=int,default=5);q.add_argument('--seed',type=int)
        if action=='submit':q.add_argument('--arm',choices=['cards','no_cards'],required=True);q.add_argument('--input',required=True)
        if action=='audit':q.add_argument('--input',required=True)
    return p
def main(argv=None):
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    args=parser().parse_args(argv)
    try:
        if args.action=='verify-package':result=verify_package()
        elif args.action=='reproduce':result=reproduce(args.output)
        elif args.action=='demo':result=demo(args.root)
        elif args.action=='generate':result=generate(args)
        elif args.action=='predict':result=predict(args)
        elif args.action=='init':result=e.initialize(Path(args.root),args.stories,args.method,count=args.count,batch_size=args.batch_size,seed=args.seed)
        elif args.action=='submit':result=e.submit(Path(args.root),args.arm,args.input)
        elif args.action=='audit':result=e.submit_audit(Path(args.root),args.input)
        else:result=getattr(e,args.action)(Path(args.root))
    except (ValueError,AssertionError,KeyError,OSError) as exc:
        print(f'{type(exc).__name__}: {exc}',file=sys.stderr);raise SystemExit(2)
    print(json.dumps(result,ensure_ascii=False,indent=2))
