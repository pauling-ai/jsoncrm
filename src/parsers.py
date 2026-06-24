"""LinkedIn MCP output parsers for jsoncrm."""

import json
from datetime import date
from pathlib import Path

from jsoncrm.schema import JSON_DB_ENCODING
from jsoncrm.utils import atomic_write_json


def cmd_parse_from_linkedin_mcp(args):
    for filename in args.files:
        path = Path(filename)
        if not path.exists():
            print(f"Error: {path} not found")
            continue

        data = json.loads(path.read_text(encoding=JSON_DB_ENCODING))
        
        if not isinstance(data, dict):
            print(f"Error: {path.name} must be a recognized MCP output format (dict)")
            continue

        people_data = []

        # Format 1: get_post_likers
        if "likers" in data:
            for l in data["likers"]:
                people_data.append({
                    "raw_name": l.get("name", ""),
                    "url": l.get("url", "")
                })
                
        # Format 2: get_inbox
        elif "conversations" in data:
            for c in data["conversations"]:
                url = c.get("thread_url") or ""
                if c.get("username"):
                    url = f"https://www.linkedin.com/in/{c['username']}/"
                people_data.append({
                    "raw_name": c.get("name", ""),
                    "url": url
                })
                
        # Format 3: search_people, get_person_profile, get_company_profile, etc.
        elif "references" in data:
            for section, refs in data["references"].items():
                for r in refs:
                    if isinstance(r, dict) and r.get("kind") == "person":
                        url = r.get("url", "")
                        if url.startswith("/"):
                            url = f"https://www.linkedin.com{url}"
                        people_data.append({
                            "raw_name": r.get("text", ""),
                            "url": url
                        })

        if not people_data:
            print(f"Error: No people records found in {path.name}. Supported formats: likers, conversations, references.")
            continue

        print(f"Converting {len(people_data)} records from {path.name} to CRM format...")
        out_data = []
        today_str = str(date.today())
        
        for p in people_data:
            raw_name = p["raw_name"]
            parts = raw_name.split("\n")
            name = parts[0].strip()
            position = parts[-1].strip() if len(parts) > 1 else ""
            if position.startswith("·"):
                position = position[1:].strip()
            company = None
            if " at " in position:
                p_parts = position.split(" at ")
                position = p_parts[0].strip()
                company = p_parts[1].strip()
            elif " @ " in position:
                p_parts = position.split(" @ ")
                position = p_parts[0].strip()
                company = p_parts[1].strip()
                
            out_data.append({
                "name": name,
                "position": position,
                "company": company,
                "linkedin_url": p["url"],
                "connected": "1st degree" in raw_name,
                "email": None,
                "contacted_at": None,
                "source": "linkedin_mcp",
                "added": today_str,
                "score": None,
                "notes": ""
            })
            
        atomic_write_json(path, out_data)
        print(f"Successfully converted {len(out_data)} records in {path.name}.")
