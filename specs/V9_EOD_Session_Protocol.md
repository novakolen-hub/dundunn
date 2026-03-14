# V9 EOD Session Protocol

## When Olen says we're done, run this checklist:

### 1. Session Summary → GitHub
Push `sessions/session_[date].md` with:
- What was built (scanner version, dashboard version, features)
- Current deploy state (what needs pasting, what's live)
- Known issues
- What's next (priority queue)

### 2. Specs & Docs → GitHub
Push any new specs, breakdowns, or reference docs to `specs/` folder.

### 3. Output Files
- Scanner `.txt` file if scanner code changed → present to Olen
- Dashboard `.html` if not already pushed to GitHub
- Any other deliverables

### 4. Memory Update
- Check if anything discussed should update memory (new terminology, workflow changes, architecture decisions)
- Use memory_user_edits tool if needed

### 5. Remind Olen to Upload to Claude Project
Be explicit about which files:
- "Upload V9_Scanner_v[version].txt to the Trading project in Claude"
- "Upload [any new spec files] to the Trading project in Claude"
- Dashboard code only if it diverged from GitHub (normally GitHub is source of truth)

### 6. Next Session Prompt
Provide a clean continuation block Olen can paste to start the next session:
```
## Continuation from [date]
- Scanner: v[x] — [deployed/needs paste]
- Dashboard: v[x] — live on GitHub Pages
- Chart Wall: v[x] — live on GitHub Pages
- Last session: [brief summary]
- Next up: [priority items]
- Known issues: [any blockers]
```

### 7. Don'ts
- Do NOT suggest ending the session — Olen decides when we're done
- Do NOT defer items to "next time" unless Olen says so
- Do NOT push session summary until Olen confirms we're wrapping up
