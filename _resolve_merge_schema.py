from pathlib import Path

p = Path("graphify/cache.py")
text = p.read_text(encoding="utf-8")
start = text.index("<<<<<<< ")
mid = text.index("=======\n")
end_mark = text.index(">>>>>>> ")
end = text.index("\n", end_mark) + 1

# During merge: HEAD = our PR branch, incoming = v8
ours = text[text.index("\n", start) + 1 : mid].strip()
theirs = text[mid + len("=======\n") : end_mark].strip()

assert ours.startswith("_AST_CACHE_SCHEMA = ")
assert theirs.startswith("_AST_CACHE_SCHEMA = ")

ours_body = ours.split("#", 1)[1].strip()
theirs_body = theirs.split("#", 1)[1].strip()
theirs_num = int(theirs.split("=", 1)[1].strip().split()[0])
new_num = theirs_num + 1

# One bump on top of current v8: fold #5338+#5357 into the lead sentence.
lead = (
    "C/C++ walk_calls: stop fall-through after unconditional return / static "
    "infinite loops (nonzero integer conditions; C does not treat while(true) as "
    "infinite because true may be a variable), resume at goto labels and switch "
    "case/default, seed preproc_elif/preproc_else as parallel reachability entries "
    "so alternate #if configs stay extracted (#5338, #5357); optional unreachable-call "
    "stderr warning (toggle API only)"
)
resolved = f"_AST_CACHE_SCHEMA = {new_num}  # {lead}; prior ({theirs_num}): {theirs_body}\n"
new = text[:start] + resolved + text[end:]
assert "<<<<<<<" not in new and ">>>>>>>" not in new
p.write_text(new, encoding="utf-8")
print(f"resolved schema {new_num}; ours lead kept folded; prior={theirs_num}")
print(resolved[:240])
