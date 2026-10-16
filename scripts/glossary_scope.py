#!/usr/bin/env python3
"""Analyze glossary batch-completion scope: which snapshot pages need chapter-alignment verification."""
import json, os, re, collections
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SNAP = ROOT / "en_snapshot"
GLOSS = ROOT / "dict" / "mistborn.json"

# book ref code -> canonical translated-book group
# translated = era1(1-3) + era2(1-3): mb1..mb6
TRANSLATED = {'mb1','mb2','mb3','mb4','mb5','mb6',
              'aol','sos','bom',          # era2 1-3 aliases
              'mbe1','mbe2','mbe3','mbe4','mbe5'}  # era1 aliases
UNTRANSLATED = {'mb7','tlm'}              # The Lost Metal
# era 1.5 short stories / other media with no zh translation in our set
NOZH = {'eltania','secret history','sh'}  # Allomancer Jak, Secret History

def book_codes(name):
    d = SNAP / name
    wt = d / "wikitext.txt"
    if not wt.exists():
        return set()
    txt = wt.read_text(encoding='utf-8', errors='replace')
    return {c.strip().lower() for c in re.findall(r'\{\{\s*book\s+ref\|([^|}]+)', txt, re.I)}

def norm(s):
    return re.sub(r'\s+\([^)]*\)$', '', s).strip().lower()

def classify(codes):
    tr = codes & TRANSLATED
    untr = codes & UNTRANSLATED
    nozh = codes & NOZH
    if codes <= nozh or (not tr and nozh):
        # only appears in untranslated-era1.5 short stories
        return 'nozh_only'
    if not codes:
        return 'no_ref'
    if tr:
        return 'verifiable'
    if untr or nozh:
        return 'others_media'
    return 'other'

def main():
    gloss = json.loads(GLOSS.read_text(encoding='utf-8'))['terms']
    folded = {k.lower() for k in gloss}
    chars = json.load(open('/tmp/char_pages.json', encoding='utf-8'))
    todo = [c for c in chars if norm(c) not in folded]
    # additionally note which already-verifiable ones exist (for tlm list dedup)
    out = []
    cnt = collections.Counter()
    for c in todo:
        codes = book_codes(c)
        k = classify(codes)
        cnt[k] += 1
        out.append({"name": c, "books": sorted(codes), "class": k})
    print("todo char pages:", len(todo), dict(cnt))
    for k in ('verifiable', 'no_ref', 'nozh_only', 'others_media', 'other', 'tlm_only'):
        names = [o['name'] for o in out if o['class'] == k]
        print(f"\n== {k} ({len(names)}) ==")
        print(' '.join(names))

if __name__ == '__main__':
    main()
