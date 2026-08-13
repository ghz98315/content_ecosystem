const TAG_PATTERN = /#([^#]+?)(?=(?:[_\s]*#)|$)/g;

export function splitSourceDescription(value?: string | null) {
  const raw = String(value || "").trim();
  const tags: string[] = [];
  for (const match of raw.matchAll(TAG_PATTERN)) {
    const tag = match[1].replace(/[_\s]+/g, "").replace(/^[#，。！？；：,!?;:、]+|[#，。！？；：,!?;:、]+$/g, "");
    if (tag && !tags.includes(tag)) tags.push(tag);
  }
  const title = (raw.includes("#") ? raw.slice(0, raw.indexOf("#")) : raw)
    .replace(/_+/g, " ")
    .replace(/\s+/g, " ")
    .replace(/^[ _，。！？；：,!?;:、]+|[ _，。！？；：,!?;:、]+$/g, "");
  return { title, tags };
}

export function compactTitle(value?: string | null, limit = 20) {
  const title = splitSourceDescription(value).title;
  return title.slice(0, limit);
}
