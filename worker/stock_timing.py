"""Lossless timed manuscript cuts, using actual subtitle character offsets."""
from stages.render import _cue_time_at_char

def timed_blocks(text,subs,target=50,minimum=40,maximum=60,char_offset=0):
    cues=subs['segments'];duration=float(subs['duration']);parts=[];begin=0;cursor=char_offset;start_time=_cue_time_at_char(cursor,cues,duration);preferred=None
    for index,char in enumerate(text):
        cursor+=int(not char.isspace());elapsed=_cue_time_at_char(cursor,cues,duration)-start_time
        if char in '。！？；，\n' and elapsed>=minimum:preferred=(index+1,cursor)
        cut=preferred if elapsed>=target and preferred else (index+1,cursor) if elapsed>=maximum else None
        if cut:
            end,position=cut;parts.append(text[begin:end]);begin=end;start_time=_cue_time_at_char(position,cues,duration);preferred=None
    if begin<len(text):parts.append(text[begin:])
    return parts or [text]
