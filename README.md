# JSONCRM

A CRM system built on top of JSON. That's right. You may be wondering why? And the answer is: why not? If this doesn't immediately tickle your hypothalamus here is the longer intro ↓↓↓

CRMs are valuable because they combine two things most companies fail to systematize: a structured database of customer relationships and a process engine that makes sure people actually do what they said they would do. Contacts, companies, deals, and activities form a living timeline of every interaction, while workflows make sure nothing quietly dies in a corner. The real power of a CRM is not the UI that guides people through a process, or the data contained in its database. It is the enforcement of consistent behavior at scale. In other words, it is the system that politely refuses to let you forget your leads.

Historically, tools like Salesforce and HubSpot wrapped this idea in large, heavy applications. But of course spreadsheets have always been here, and proved you could get surprisingly far with something much simpler. Rows become records, tabs become pipeline stages, and humans drag deals around and call it a process. It works, until it very much does not. No enforcement, no structure, no automation. Just optimism and increasingly questionable data. One lesson is: the CRM is not the interface. It is the combination of state and process. The interface is just the surface.

JSONCRM takes this one step further by making the state itself the interface. Instead of hiding data inside an application, everything lives as structured JSON files. Contacts, deals, pipelines. You can open them, edit them, diff them, and roll them back. Git handles history and collaboration. Code handles the process, enforcing stage transitions, next actions, and updates. No mystery, no black box. Just files as the source of truth and tools making sure things happen the way they should.

Now, if you are a human reading this, then you may think: well, we already have databases. And it's true! We have databases and they are great. But as databases become more complex and rich they become harder to manipulate, and then you need UIs and so on and we are back to the same place. As a human you may be very good using CRM user interfaces. But guess who's not that good? That's right, AI agents.

The real shift is that JSONCRM is native to AI agents. JSON is exactly the kind of structure language models can read and write without friction. Instead of forcing an agent to click through a UI, you give it the actual state of the business. It can reason over deals, update records, draft follow ups, and trigger actions through tools. Humans and agents now operate on the same substrate: inspectable files, auditable changes, and explicit workflows. The result is a CRM that is not just simpler or more flexible, but fundamentally different. A git backed, agent native system where customer data, process, and automation are all transparent, programmable, and shared between humans and AI.

On top of that, extensions become trivial instead of a multi month integration project. Because everything is just files and tools, you can plug in new capabilities as simple services that read and write JSON. An MCP server can watch for new leads and enrich them with data from external sources. Another tool can sync activity with email, trigger campaigns, or update product usage signals. Want to score deals, enrich contacts, or run outbound sequences? Add a tool that reads the files, writes updates, and you are done. No SDK hell, no brittle UI automation, no fighting someone else’s data model. Just composable building blocks operating on shared state. The result is a system where adding new capabilities can be done with a tiny script, not negotiating with a platform.

This project is hosted [here](https://www.jsoncrm.dev)

## License

This project is licensed under the GNU Affero General Public License v3.0 only.

Commercial licensing is available for organizations that want to use this software
without the obligations of the AGPL. Contact: info@pauling.ai

## Copyright

Copyright (C) 2026 Pauling.AI
