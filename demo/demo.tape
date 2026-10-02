# The demo, as a script: `make demo` records it to demo/demo.mp4 from a clean
# shell with no history, so a rerun after any change shows the same thing.
Output demo/demo.mp4

Set Shell "bash"
Set FontSize 13
Set Width 1440
Set Height 900
Set Padding 24
Set TypingSpeed 25ms
Set WaitTimeout 120s
Env HISTFILE "/dev/null"
Env PS1 "$ "

Hide
Type "clear" Enter
Show

Type "# The specification is this code's input. The model it loads must match the published tag." Enter
Type "make model-verify" Enter
Wait /^\$\s*$/
Sleep 3s

Type "clear" Enter
Type "# One course through the gateway: brief, outline, nodes, publication, rollback - then seven inputs it must refuse." Enter
Type "make run" Enter
Sleep 16s

Type "clear" Enter
Type "# Five refusals, each from the engine that owns it, each with something to act on." Enter
Type "make refusals" Enter
Sleep 14s

Type "clear" Enter
Type "# What a refusal hands back: the path from a node to a source its audience cannot see." Enter
Type "cat examples/04-*/input.yaml | head -24; echo ---; cat examples/04-*/refusal.yaml" Enter
Sleep 9s

Type "clear" Enter
Type "# Every test, the layer that owns it, and what it expects." Enter
Type "sed -n '5,20p' docs/test-matrix.md | cut -c1-150" Enter
Sleep 10s
