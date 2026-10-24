"""Bounded local re-recognition of long ASR omissions, without forcing a script."""
import difflib,subprocess
from pathlib import Path
from external_alignment import comparable
from narration import split_semantic_units,SUBTITLE_MAX_CHARS

def missing_windows(text,words,duration):
    source=''.join(comparable(u['text']) for u in split_semantic_units(text,max_chars=SUBTITLE_MAX_CHARS))
    transcript='';indices=[]
    for index,word in enumerate(words):
        token=comparable(word['word']);transcript+=token;indices.extend([index]*len(token))
    if not indices:return []
    matcher=difflib.SequenceMatcher(None,source,transcript,autojunk=False)
    if sum(b.size for b in matcher.get_matching_blocks())/max(1,len(source),len(transcript))<.8:return []
    windows=[]
    for kind,a,b,c,d in matcher.get_opcodes():
        if kind!='delete' or not 24<b-a<=120 or c==0 or c>=len(indices):continue
        left=float(words[indices[c-1]]['end']);right=float(words[indices[c]]['start'])
        if right-left<max(1,(b-a)/15) or right-left>20:continue
        start=max(0,left-2);end=min(duration,right+2)
        # Include entire boundary words so no syllable is lost during splicing.
        start=min(start,min((float(w['start']) for w in words if float(w['start'])<start<float(w['end'])),default=start))
        end=max(end,max((float(w['end']) for w in words if float(w['start'])<end<float(w['end'])),default=end))
        if windows and start<=windows[-1][1]:windows[-1]=(windows[-1][0],max(end,windows[-1][1]))
        else:windows.append((start,end))
    return [window for window in windows if window[1]-window[0]<=25][:3]

def repair_omissions(text,words,duration,audio,tmp,ffmpeg,recognize):
    reports=[];result=list(words)
    for index,(start,end) in enumerate(missing_windows(text,words,duration)):
        try:
            path=Path(tmp)/f'asr-repair-{index}.wav'
            subprocess.run([ffmpeg,'-v','error','-y','-ss',str(start),'-t',str(end-start),'-i',str(audio),'-ac','1','-ar','16000',str(path)],check=True,capture_output=True,timeout=45)
            segments,_,_=recognize(str(path),vad_filter=False)
            fresh=[{'word':w.word,'start':round(w.start+start,3),'end':round(w.end+start,3),'probability':round(w.probability,4)} for segment in segments for w in (segment.words or [])]
            fresh=[w for w in fresh if start<=w['start']<=w['end']<=min(duration,end)+.05]
            if not fresh:raise ValueError('empty localized recognition')
            candidate=[w for w in result if float(w['end'])<=start]+fresh+[w for w in result if float(w['start'])>=end]
            expected=''.join(comparable(u['text']) for u in split_semantic_units(text,max_chars=SUBTITLE_MAX_CHARS))
            score=lambda rows:difflib.SequenceMatcher(None,expected,''.join(comparable(w['word']) for w in rows),autojunk=False).ratio()
            accepted=score(candidate)>score(result)
            if accepted:result=candidate
            reports.append({'start':round(start,3),'end':round(end,3),'vad_filter':False,'accepted':accepted})
        except Exception as exc:reports.append({'start':round(start,3),'end':round(end,3),'accepted':False,'error_type':type(exc).__name__})
    return result,reports
