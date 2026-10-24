"""Indexed, bounded query planning; partial model output never drops a paragraph."""
import hashlib,json,re,time

def fallback_query(text,category):
    query='peaceful nature walking outdoors';role='lifestyle'
    if category=='health':
        query='sunny active adults healthy lifestyle'
        for pattern,choice in [('饮食|食物|食材|蔬菜|水果|吃','healthy food vegetables meal preparation'),('睡眠|睡觉|卧室|作息|失眠','peaceful bedroom restful sleep'),('运动|散步|锻炼|徒步','active adults walking sunny park'),('家人|朋友|陪伴|社交|连接','happy family friends outdoor activity'),('学习|记忆|思考|阅读','older adults reading learning daylight')]:
            if re.search(pattern,text):query=choice;break
        if re.search('原理|结构|机制',text) and re.search('大脑|神经|血管|细胞',text):query='brain neural anatomy educational diagram';role='explanation'
    return {'query':query,'role':role,'entity':'','reason':'模型规划缺项，按本段主题补充检索词，请预览确认','planning_fallback':True}

def batched_queries(blocks,category,policy,client,model,instructions,cache):
    result=[];cache.mkdir(parents=True,exist_ok=True)
    for start in range(0,len(blocks),8):
        batch=blocks[start:start+8]
        identity=json.dumps(['indexed-query-v1',model,category,policy,instructions,start,batch],ensure_ascii=False,sort_keys=True)
        path=cache/('planner-'+hashlib.sha256(identity.encode()).hexdigest()+'.json')
        saved=None
        try:
            if path.exists() and time.time()-path.stat().st_mtime<86400:
                saved=json.loads(path.read_text(encoding='utf-8'))
                if not isinstance(saved,list) or len(saved)!=len(batch) or not all(isinstance(x,dict) and str(x.get('query','')).strip() for x in saved):saved=None
        except (ValueError,OSError):pass
        if saved is not None:result.extend(saved);continue
        response=client.chat.completions.create(model=model,messages=[{'role':'system','content':instructions+' 输出index必须等于输入index，不能合并或遗漏段落。'},{'role':'user','content':json.dumps({'category':category,'paragraphs':[{'index':start+i,'text':text} for i,text in enumerate(batch)]},ensure_ascii=False)}],response_format={'type':'json_object'},temperature=.3)
        try:items=json.loads(response.choices[0].message.content or '{}').get('items',[])
        except (ValueError,AttributeError):items=[]
        if not isinstance(items,list):items=[]
        mapped={};duplicates=set()
        positional=len(items)==len(batch) and all(isinstance(item,dict) and 'index' not in item for item in items)
        for offset,item in enumerate(items):
            if not isinstance(item,dict):continue
            index=start+offset if positional else item.get('index')
            if isinstance(index,bool) or not isinstance(index,int) or not start<=index<start+len(batch) or not isinstance(item.get('query'),str) or not item['query'].strip():continue
            if index in mapped:duplicates.add(index)
            mapped[index]=item
        resolved=[mapped[index] if index in mapped and index not in duplicates else fallback_query(blocks[index],category) for index in range(start,start+len(batch))]
        # Only fully model-authored batches are cached, allowing missing items to improve on a later search.
        if not any(item.get('planning_fallback') for item in resolved):
            try:path.write_text(json.dumps(resolved,ensure_ascii=False),encoding='utf-8')
            except OSError:pass
        result.extend(resolved)
    return result
