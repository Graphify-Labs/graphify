# graphify reference: GitHub clone and cross-repo aggregation

### Step 0 - Clone GitHub repo(s) (only if a GitHub URL was given)

```bash
graphify clone https://github.com/OWNER/REPO --branch BRANCH --out LOCAL_PATH
graphify extract LOCAL_PATH
```

For several repositories, build each project independently, then register each project directory or native store:

```bash
graphify global add repo-a
graphify global add repo-b/graphify-out/graph.helix
```

Global aggregation reads native snapshots. Do not combine storage files or invoke removed merge commands.
