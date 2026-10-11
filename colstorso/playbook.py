"""KPI catalogue, root causes and guided-action playbook (original content)."""

KPIS = {
  "sales":      dict(label="Category sales", group="Sales", level="cat", unit="$", better="higher",
                     scaler="share of parent department sales"),
  "waste":      dict(label="Waste / spoilage", group="Loss", level="dept", unit="%", better="lower",
                     scaler="waste as % of department sales"),
  "invacc":     dict(label="Inventory accuracy (phantom stock)", group="Loss", level="store", unit="%", better="higher",
                     scaler="cycle-count accuracy vs same-format stores"),
  "labor":      dict(label="Labor hours to budget", group="Labor", level="store", unit="%", better="lower",
                     scaler="worked hours / budgeted hours"),
  "overtime":   dict(label="Premium / overtime hours", group="Labor", level="store", unit="%", better="lower",
                     scaler="overtime as % of worked hours"),
  "conversion": dict(label="Conversion", group="Customer", level="store", unit="%", better="higher",
                     scaler="transactions / door traffic"),
  "csat":       dict(label="Customer satisfaction", group="Customer", level="store", unit="pts", better="higher",
                     scaler="survey score vs same-format stores"),
  "attach":     dict(label="Attachment rate", group="Customer", level="store", unit="%", better="higher",
                     scaler="baskets with an add-on item"),
  "gapscan":    dict(label="Gap-scan compliance", group="Compliance", level="store", unit="%", better="higher",
                     scaler="scheduled gap scans completed"),
  "cash":       dict(label="Cash over / short", group="Compliance", level="store", unit="$", better="zero",
                     scaler="absolute till variance"),
  "equipment":  dict(label="Equipment uptime", group="Operations", level="cat", unit="$", better="higher",
                     scaler="sales vs own 8-week run-rate"),
  "custom":     dict(label="Custom / central", group="Operations", level="store", unit="", better="higher", scaler="n/a"),
  "dc_quality": dict(label="DC load quality", group="Supply chain", level="store", unit="#", better="lower", scaler="flags"),
}

ROOT_CAUSES = {
  "sales": ["Product out of stock / low on-hand", "Shelf gaps or poor facings", "Planogram not followed",
            "Promotion or price label missing", "Product in the wrong location / blocked", "Local competitor activity",
            "Range not suited to local customers"],
  "waste": ["Over-ordering vs demand", "Markdown / reduction scans done late", "Poor stock rotation (FIFO)",
            "Over-production of prepared food", "Cold-chain or equipment issue"],
  "invacc": ["Unrecorded waste or damages", "Receiving errors / short deliveries", "Theft", "Mis-scans at checkout"],
  "labor": ["Schedule built above model", "Call-outs covered with extra shifts", "Tasks taking longer than standard",
            "Unplanned deliveries or events"],
  "overtime": ["Last-minute call-outs", "Schedule not published on time", "Too few part-time staff",
               "Shift swaps not approved properly"],
  "conversion": ["Long queues / too few tills open", "Key lines out of stock", "Staff not on the floor at peak",
                 "Self-checkout downtime"],
  "csat": ["Queue times", "Staff availability / friendliness", "Store cleanliness", "Product availability"],
  "attach": ["Add-on not offered at till", "Accessories not merchandised near hero items", "Team not trained on add-ons"],
  "gapscan": ["Scans skipped on busy days", "Handheld device issues", "Unclear ownership of the scan"],
  "cash": ["Till counting errors", "Change-fund procedure not followed", "Possible internal theft"],
  "equipment": ["Machine broken / out of service", "Supplies not refilled", "Display switched off"],
  "custom": ["Other"], "dc_quality": ["Picking error", "Loading / wrapping error", "Damaged in transit"],
}

ACTIONS = {
  "Fix availability & ordering": "Check on-hand vs shelf, correct the order quantity, chase short deliveries.",
  "Re-merchandise & fix facings": "Walk the bay with the planogram, restore facings, clear blocked product.",
  "Promotion & signage fix": "Confirm every promo and price label is up and correct; add secondary display.",
  "Coach the team": "Run a 10-minute huddle on the standard and check back mid-week.",
  "Process / routine change": "Change who does what and when (e.g. move markdowns earlier, add a scan slot).",
  "Schedule rebalance": "Move hours to peak, remove low-value hours, publish on time.",
  "Ordering reduction": "Cut order quantity on the worst-waste lines by 10–20% and review daily.",
  "Repair / maintenance ticket": "Raise a maintenance ticket and set a temporary workaround.",
}

GUIDANCE = {
  "sales": "Start at the shelf: is the product there, is it where the planogram says, is the price right? "
           "Most gaps come from availability or location, not demand.",
  "waste": "Pull the last 7 days of waste by line. Look for lines wasted on most days — those are ordering issues.",
  "invacc": "Count the 10 lines with the largest stock drift first. Record every damage before it goes in the bin.",
  "labor": "Compare the published schedule to the labor model hour by hour; look for overlap at quiet times.",
  "overtime": "List every overtime shift last week and why it happened. Most are call-outs that could be covered by part-timers.",
  "conversion": "Watch the store at peak for 20 minutes: queues, empty shelves, staff on the floor?",
  "csat": "Read this week's verbatims and group them; fix the most common complaint first.",
  "attach": "Put the add-on product within arm's reach of the hero product and brief the till team.",
  "gapscan": "Assign the scan to a named person on each shift and check completion at handover.",
  "cash": "Do a double-count on every till for 3 days and review the change-fund log.",
  "equipment": "Check the machine now. If it is down, raise a ticket and put up a notice for customers.",
  "custom": "Follow the instructions from the central team.",
  "dc_quality": "Review the pallet history and coach the picker/loader on the standard that was missed.",
}

SURVEY_CONCEPTS = {
  "Staffing shortfall": ["short staffed", "call out", "callout", "understaffed", "no cover", "sick"],
  "Late or short deliveries": ["delivery", "truck", "short shipped", "late", "dc", "pallet"],
  "Broken equipment": ["broken", "machine", "freezer", "fridge", "down", "repair", "leak"],
  "Pricing & signage errors": ["price", "label", "tag", "signage", "ticket"],
  "Shelf gaps / planogram": ["gap", "planogram", "facing", "empty shelf", "shelf"],
  "Theft & security": ["theft", "stolen", "shoplift", "security"],
  "Cleanliness": ["dirty", "clean", "spill", "litter", "toilet"],
  "Out of stock": ["out of stock", "oos", "no stock", "sold out"],
}

DEFAULT_PERMISSIONS = {
  "hq_admin": ["architect", "campaigns", "approve", "send_mission", "tasks_admin", "surveys_admin", "comms", "data",
               "users", "impact", "visits", "team", "dc"],
  "central_analyst": ["send_mission", "tasks_admin", "surveys_admin", "comms", "data", "impact", "campaigns", "team"],
  "regional_manager": ["approve", "send_mission", "comms", "impact", "visits", "team"],
  "district_manager": ["approve", "send_mission", "visits", "team", "comms"],
  "store_manager": ["team"],
  "associate": [],
  "dc_manager": ["dc"],
  "ai_agent": [],
}

ROLE_LABELS = {"hq_admin": "HQ / Central Ops admin", "central_analyst": "Central analytics", "regional_manager": "Regional manager",
  "district_manager": "District manager", "store_manager": "Store manager", "associate": "Store associate",
  "dc_manager": "DC manager", "ai_agent": "AI agent"}
