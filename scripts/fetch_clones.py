
import os
import json
import requests
import sys

# Configuration
TOKEN = os.environ.get("TRAFFIC_TOKEN")
REPO_OWNER = os.environ.get("GITHUB_REPOSITORY_OWNER") # e.g., 'shrey'
DATA_FILE = "traffic_data.json"
README_FILE = "README.md"
API_BASE = "https://api.github.com"

if not TOKEN:
    print("Error: TRAFFIC_TOKEN environment variable not set.")
    sys.exit(1)

if not REPO_OWNER:
    # Fallback or try to get from user info if running locally without GITHUB action envs
    # For now, we assume it's set or we might fetch the authenticated user
    print("Warning: GITHUB_REPOSITORY_OWNER not set. Fetching current user...")
    headers = {"Authorization": f"token {TOKEN}"}
    r = requests.get(f"{API_BASE}/user", headers=headers)
    if r.status_code == 200:
        REPO_OWNER = r.json()["login"]
    else:
        print("Error: Could not determine repository owner.")
        sys.exit(1)

HEADERS = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_repos():
    repos = []
    page = 1
    while True:
        url = f"{API_BASE}/users/{REPO_OWNER}/repos?per_page=100&page={page}"
        r = requests.get(url, headers=HEADERS)
        if r.status_code != 200:
            print(f"Error fetching repos: {r.status_code} {r.text}")
            break
        data = r.json()
        if not data:
            break
        repos.extend(data)
        page += 1
    return repos

def get_traffic(repo_name):
    url = f"{API_BASE}/repos/{REPO_OWNER}/{repo_name}/traffic/clones"
    r = requests.get(url, headers=HEADERS)
    if r.status_code != 200:
        print(f"Error fetching traffic for {repo_name}: {r.status_code}")
        return None
    return r.json()

def update_readme(stats_markdown):
    with open(README_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    start_marker = "<!-- CLONES_START -->"
    end_marker = "<!-- CLONES_END -->"

    if start_marker not in content or end_marker not in content:
        print("Error: Markers not found in README.md")
        return

    start_index = content.find(start_marker) + len(start_marker)
    end_index = content.find(end_marker)

    new_content = content[:start_index] + "\n" + stats_markdown + "\n" + content[end_index:]
    
    with open(README_FILE, "w", encoding="utf-8") as f:
        f.write(new_content)

def main():
    print(f"Fetching traffic data for {REPO_OWNER}...")
    data = load_data()
    repos = get_repos()
    
    overall_clones = 0
    overall_unique = 0
    repo_stats = []

    for repo in repos:
        name = repo["name"]
        print(f"Processing {name}...")
        
        traffic = get_traffic(name)
        if not traffic:
            continue
            
        # Update historical data
        if name not in data:
            data[name] = {"count": 0, "uniques": 0, "history": {}}
        
        # Merge daily traffic to history to avoid losing data after 14 days
        # We store timestamp -> {count, uniques}
        # Note: deduplication happens by timestamp key
        for entry in traffic.get("clones", []):
            timestamp = entry["timestamp"]
            data[name]["history"][timestamp] = {
                "count": entry["count"],
                "uniques": entry["uniques"]
            }
            
        # Recalculate totals from history (this ensures we keep accumulating)
        # However, simply summing history might overcount if we sum 'uniques' wrongly.
        # 'count' is safe to sum. 'uniques' is tricky because the same user cloning on different days counts as unique each day but 1 unique total.
        # GitHub's API gives a 'count' and 'uniques' for the 14-day window.
        # A simple accumulation strategy for 'count' is: sum of all daily counts.
        # A simple accumulation strategy for 'uniques' is impossible to be perfect without raw logs.
        # We will approximate 'uniques' by taking the max seen 'uniques' for the repo OR just sum daily uniques (which is an upper bound).
        # Better approach: We trust the "total" from GitHub for the current window, and add it to a "archived" total? No, overlapping windows make that hard.
        
        # Strategy: We will trust our stored daily history.
        # Total Clones = Sum of all 'count' in history.
        # Unique Cloners = Sum of 'uniques' in history (Upper bound, assumes distinct users per day).
        # This is the best we can do with the API limitations.
        
        total_clones = sum(d["count"] for d in data[name]["history"].values())
        total_unique = sum(d["uniques"] for d in data[name]["history"].values())
        
        data[name]["count"] = total_clones
        data[name]["uniques"] = total_unique
        
        if total_clones > 0:
             repo_stats.append((name, total_clones, total_unique))
             overall_clones += total_clones
             overall_unique += total_unique

    save_data(data)

    # Sort by clones (descending)
    repo_stats.sort(key=lambda x: x[1], reverse=True)
    
    # Generate Markdown
    # We'll show top 5 repos and a total
    
    md_lines = ["| Repository | Total Clones | Unique Cloners |", "| :--- | :---: | :---: |"]
    md_lines.append(f"| **All Repositories** | **{overall_clones}** | **{overall_unique}** |")
    
    for name, clones, unique in repo_stats[:10]: # Top 10
        # Link to the repo
        link = f"[{name}](https://github.com/{REPO_OWNER}/{name})"
        md_lines.append(f"| {link} | {clones} | {unique} |")

    update_readme("\n".join(md_lines))
    print("Done!")

if __name__ == "__main__":
    main()
