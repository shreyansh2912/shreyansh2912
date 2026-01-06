
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
    # Fetch Clones
    headers_clones = HEADERS.copy()
    url_clones = f"{API_BASE}/repos/{REPO_OWNER}/{repo_name}/traffic/clones"
    r_clones = requests.get(url_clones, headers=headers_clones)
    
    # Fetch Views
    headers_views = HEADERS.copy()
    url_views = f"{API_BASE}/repos/{REPO_OWNER}/{repo_name}/traffic/views"
    r_views = requests.get(url_views, headers=headers_views)

    if r_clones.status_code != 200 or r_views.status_code != 200:
        print(f"Error fetching traffic for {repo_name}: Clones:{r_clones.status_code} Views:{r_views.status_code}")
        return None

    return {
        "clones": r_clones.json().get("clones", []),
        "views": r_views.json().get("views", [])
    }


def main():
    print(f"Fetching traffic data for {REPO_OWNER}...")
    data = load_data()
    repos = get_repos()
    
    overall_clones = 0
    overall_unique_cloners = 0
    overall_views = 0
    overall_unique_visitors = 0
    
    repo_stats = []

    for repo in repos:
        name = repo["name"]
        print(f"Processing {name}...")
        
        traffic = get_traffic(name)
        if not traffic:
            continue
            
        # Initialize data structure
        if name not in data:
            data[name] = {
                "clones_history": {},
                "views_history": {}
            }
        
        # Ensure older format is upgraded if needed
        if "history" in data[name]: # Migration from old format
             # Assume old history was clones
             data[name]["clones_history"] = data[name]["history"]
             del data[name]["history"]
             if "views_history" not in data[name]:
                 data[name]["views_history"] = {}

        # Process Clones
        for entry in traffic["clones"]:
            timestamp = entry["timestamp"]
            data[name]["clones_history"][timestamp] = {
                "count": entry["count"],
                "uniques": entry["uniques"]
            }

        # Process Views
        for entry in traffic["views"]:
            timestamp = entry["timestamp"]
            data[name]["views_history"][timestamp] = {
                "count": entry["count"],
                "uniques": entry["uniques"]
            }
            
        # Calculate Totals from History
        total_clones = sum(d["count"] for d in data[name]["clones_history"].values())
        unique_cloners = sum(d["uniques"] for d in data[name]["clones_history"].values())
        
        total_views = sum(d["count"] for d in data[name]["views_history"].values())
        unique_visitors = sum(d["uniques"] for d in data[name]["views_history"].values())
        
        # Add to overall
        overall_clones += total_clones
        overall_unique_cloners += unique_cloners
        overall_views += total_views
        overall_unique_visitors += unique_visitors

        # Append to list if there is any activity
        if total_clones > 0 or total_views > 0:
             repo_stats.append({
                 "name": name,
                 "clones": total_clones,
                 "unique_cloners": unique_cloners,
                 "views": total_views,
                 "unique_visitors": unique_visitors
             })

    save_data(data)

    # Sort by views (descending)
    repo_stats.sort(key=lambda x: x["views"], reverse=True)
    
    # Generate Markdown
    md_lines = [
        "| Repository | Views | Unique Visitors | Clones | Unique Cloners |", 
        "| :--- | :---: | :---: | :---: | :---: |"
    ]
    
    # Total Row
    md_lines.append(f"| **All Repositories** | **{overall_views}** | **{overall_unique_visitors}** | **{overall_clones}** | **{overall_unique_cloners}** |")
    
    for repo in repo_stats[:10]: # Top 10
        link = f"[{repo['name']}](https://github.com/{REPO_OWNER}/{repo['name']})"
        md_lines.append(f"| {link} | {repo['views']} | {repo['unique_visitors']} | {repo['clones']} | {repo['unique_cloners']} |")

    update_readme("\n".join(md_lines))
    print("Done!")

if __name__ == "__main__":
    main()
