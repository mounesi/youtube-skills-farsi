# Bugs found and fixed in the upstream pack

Audit of Jakeschincariol/youtube-agent-skill @ a2feb21: 71 suspected bugs, each re-checked by an independent skeptic; 46 confirmed and fixed (regression tests in `tests/upstream/`), 25 refuted.

| Severity | File | Bug |
|---|---|---|
| high | `skills/yt-edit/deadair.py` | Whisper JSON given as a top-level list crashes (d.get on a list) |
| high | `skills/yt-edit/deadair.py` | Overlapping cuts are double-counted: removed > duration, negative runtime, '140% shorter' |
| high | `skills/yt-edit/deadair.py` | Lines after a cue are glued onto it: WebVTT cue identifiers and NOTE blocks pollute text, hiding FILLER and REPEAT |
| high | `skills/yt-edit/deadair.py` | Whisper JSON given as a top-level list crashes chapters.py (AttributeError) |
| high | `skills/yt-retention/retention.py` | Cliffs are picked from the top 5 by drop rate and only then filtered by size (d > 0.8), so real cliffs below rank 5 disappear |
| high | `skills/yt-retention/retention.py` | Axis detection max(xs) <= 100.5 treats any video of 100 s or less with a seconds axis (every Short) as a percent axis |
| high | `skills/yt-script/hooks.json` | 8 of the 21 formulas' own example hooks are classified as a different formula or 'Unclassified' (ties go to whichever formula comes first in the file; patterns miss spelled-out numbers) |
| high | `skills/yt-viral/swipe.py` | yt-dlp output, which SKILL.md recommends, is silently read as 0 videos (wants 'videos'/'views', yt-dlp gives 'entries'/'view_count') |
| medium | `skills/yt-chapters/chapters.py` | Duration taken from the LAST cue's end, not the max end: overlapping cues truncate the last chapter and drop its text |
| medium | `skills/yt-edit/deadair.py` | UTF-8 BOM makes whisper JSON crash (and a BOM before a timestamp-first SRT drops cue 1) |
| medium | `skills/yt-edit/deadair.py` | Cue text that is a bare number is dropped, so spoken speech is reported and cut as DEAD air |
| medium | `skills/yt-edit/deadair.py` | REPEAT misses the common case: aborted first take shorter than 5 words |
| medium | `skills/yt-edit/deadair.py` | norm() strips digits, so different numbered sentences are flagged as restarts |
| medium | `skills/yt-edit/deadair.py` | FILLER regex fails on ?, !, ellipsis and markup, so most real filler cues are missed |
| medium | `skills/yt-edit/deadair.py` | YouTube auto-caption VTT (recommended in SKILL.md) is not handled: inline <c>/timestamp tags kept and rolling duplicate lines produce false REPEATs |
| medium | `skills/yt-package/title.py` | Thumbnail word limit is off by one: 4 words pass although SKILL.md and the tool's own message say three is the maximum |
| medium | `skills/yt-package/title.py` | A flag with no value crashes with IndexError (--title or --thumb as the last argument, or --title followed by --json) |
| medium | `skills/yt-package/title.py` | File mode works only when the file is the first argument, so `--thumb X titles.txt` prints usage instead of ranking |
| medium | `skills/yt-package/title.py` | 'no number, date or name' check detects only digits, so titles with a name or a written date get the issue |
| medium | `skills/yt-retention/SKILL.md` | The documented `--transcript` example silently does nothing on a percent-axis export (no --duration given) |
| medium | `skills/yt-retention/retention.py` | SLIDE is an unweighted mean of per-segment rates over everything after the hook, so it includes the cliffs and is dominated by short-span segments |
| medium | `skills/yt-script/hookscore.py` | Lines are filtered with strip() but scored unstripped, so a BOM or leading spaces break every ^-anchored formula pattern (Question, List, Direct Address) and the BOM leaks into output |
| medium | `skills/yt-script/hookscore.py` | words() keeps '.' inside tokens, so filler/vague words followed by a full stop are not detected (and a lone '.' counts as a word for brevity) |
| medium | `skills/yt-script/hookscore.py` | --hook without a value crashes with IndexError (also '--hook --json') |
| medium | `skills/yt-script/hookscore.py` | A missing/mistyped input file prints the help text and exits 0 (success); exit code logic is inverted |
| medium | `skills/yt-viral/swipe.py` | Missing/null views counted as 0 and pulled into the median, which hides real outliers (median 0 -> every multiple 0) |
| medium | `skills/yt-viral/swipe.py` | title: null crashes classify() with TypeError |
| medium | `skills/yt-viral/swipe.py` | channel: null crashes the text report with TypeError |
| low | `README.md` | README says 'Every skill reads that file' (voice.md), but 5 of the 11 SKILL.md files never mention it |
| low | `skills/yt-chapters/chapters.py` | Cues straddling a chapter boundary are dropped from both chapters' title text |
| low | `skills/yt-chapters/chapters.py` | --target argument parsing crashes or is silently ignored |
| low | `skills/yt-edit/deadair.py` | ZeroDivisionError when the last cue ends at 0 (dur == 0) |
| low | `skills/yt-edit/deadair.py` | Empty-text whisper segments are kept and count as speech, hiding long dead air |
| low | `skills/yt-edit/deadair.py` | Cues are not sorted and duration is the last cue's end, not the max end |
| low | `skills/yt-edit/deadair.py` | Argument parsing: --floor=X silently ignored, --floor without value crashes, numeric filenames and negative floors break path detection |
| low | `skills/yt-edit/deadair.py` | Whisper JSON detected only by lowercase '.json' extension; '.JSON' is parsed as SRT and yields 0 cues |
| low | `skills/yt-edit/deadair.py` | VTT cue identifiers and NOTE lines leak into cue text (and so into chapter draft titles) |
| low | `skills/yt-package/title.py` | A UTF-8 BOM in titles.txt is kept in the first title: the title gets the wrong character count and the BOM appears in the output |
| low | `skills/yt-package/title.py` | The mobile preview drops a whole word that fits exactly in the first 40 characters |
| low | `skills/yt-package/title.py` | The vague-word list contains 'mindblowing', but the tokenizer splits on hyphens, so 'mind-blowing' is never flagged |
| low | `skills/yt-package/title.py` | Passing a directory as the input file crashes with IsADirectoryError |
| low | `skills/yt-retention/retention.py` | Bad CLI argument handling: --duration/--transcript with no value give an IndexError traceback, a non-numeric value gives a ValueError traceback, the --duration value is not removed from the positional args, and zero/negative durations are accepted |
| low | `skills/yt-retention/retention.py` | A non-numeric cell is dropped instead of kept in place, so the columns shift; mm:ss positions are not parsed at all |
| low | `skills/yt-script/hookscore.py` | The pronoun 'I' (and any capitalised first word of a 2nd sentence) is counted as a proper noun, inflating SPECIFICITY by +6 each |
| low | `skills/yt-viral/swipe.py` | --min argument handling: '--min=3' silently ignored, '--min' with no value crashes, a numeric file name is dropped |
| low | `skills/yt-viral/swipe.py` | Tie-break differs from hookscore.py, so the same title gets a different formula in the two tools |
