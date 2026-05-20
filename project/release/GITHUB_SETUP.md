# Anonymous GitHub Repository Setup

Step-by-step guide to create the anonymous review repository with realistic commit history.

## Step 1: Create anonymous GitHub account

1. Open a private/incognito browser window
2. Register a new GitHub account with a generic name, e.g., `qac-calibration-2026`
3. Use a throwaway email address (e.g., ProtonMail)
4. Do NOT link to your real GitHub account

## Step 2: Create the repo

```bash
# On GitHub: New repo → Name: itb-qcts → Private → Initialize with README
# Then clone and set up:
git clone https://github.com/qac-calibration-2026/itb-qcts.git
cd itb-qcts
```

## Step 3: Populate with historical commits

Copy the release folder contents and run the historical commit script:

```bash
# Copy release files into the cloned repo
cp -r /path/to/project/release/* .

# Run the historical commit generator
bash git_init_with_history.sh
```

## Step 4: Verify before submission

```bash
# Make sure no identifying info leaks
grep -r "legacccy\|yj200\|余嘉\|xjtlu\|liverpool" . --include="*.py" --include="*.md"
git log --oneline | head -20
```

## Step 5: Make repo public just before submission

Settings → General → Danger Zone → Change visibility → Public

## Timeline

| When | Action |
|------|--------|
| W7 (July 1-7) | Create account + repo + push skeleton |
| W8 (July 8-14) | Final code cleanup + verify no leaks |
| Submission day | Make public; add link to paper |
