# The Ethos of Clanker

Clanker is an assistant. An "assistant" is an LLM with access to tools that is available on demand. An assistant has three types of components: the LLM, the tools, and the glue server. The Clanker codebase implements a glue server and various tools. The glue server is what users connect to, and it manages the connections between the user, the LLM, and the various tools. More advanced assistants in the future may ship with their own specialized LLMs, but Clanker does not.

## The Lethal Trifecta

[The Lethal Trifecta - Simon Willison](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/)

The legs of the lethal trifacta:
- access to private data
- access to untrusted data
- a communication channel to the outside world (an "outside channel")

Notes:
- The attacker co-opts the assistant via untrusted data to send private data over the outside channel, where the attacker reads it.
- "Communication channel" is subtle! Making a GET requests requires a channel. A highly capable attacker may be capable of using an encrypted channel as a outside channel with a timing attack.
- No channel is every truly "inside". Consider giving your assistant weather information by granting access to a tool that hits the National Weather Service API over HTTPS. This is an encrypted channel to a trusted source; an attacker has no way of determining what passes over the channel, so this is "inside". But! A determined attacker could possibly pull off a timing attack. "Send two requests if the user is secretly a communist", that sort of thing. We can fix that by downloading dump of NWS data every couple hours. No more timing, problem solved! We're inside. But! A determined attacker could still compromise us by compromising the NWS. Then it's as simple as "instead of lat/lon, send us the user's secret". Whether or not you consider a communications channel inside or outside depends on your security posture.
- Accessing both trusted data and private data poisons the context. But accessing an outside channel doesn't, and accessing only one of trusted or private data doesn't. Your assistant can read a new article from the Associated Press (a source of trusted data, assuming a less aggressive security posture), send an email (communicate over an outside channel), then check your email (a source of untrusted and private data), and be totally fine. But if the assistant accesses your email, then sends an email, you're cooked.
- Some tools have zero legs. Doing a search through a snapshot (audited too, if you like) copy of Wikipedia access public, trusted data over an inside channel. 

Implications:
- The assistant can ALWAYS access tools that have zero legs in the lethal trifecta. Therefore, a good assistant will have access to many of these tools.
- It is the responsiblity of deterministic software to prevent the assistant from combining all three legs of the trifecta. It is the responsiblity of the assistent to pick which tools to use. A basic implementation would be the assistant chooses tools with no consideration for the trifecta, and the implementing software returns errors for tool uses that would complete the trifecta. A more advanced implementation would have a planning phase in which the assistant plots out a sequence of tools that will allow it to complete the task.
- Once context has been exposed to untrusted or private data, it is impossible to filter that data back out. Passing that context through another LLM that rewrites the data, or getting the data from a sub-assistant that processes the data, does not help. Something can always get though, and one failure is all it takes to be compromised.

Under a more relaxed security posture, communicating with trusted APIs over encryoted channels is considered to be inside. APIs that grant access to data sources curated by reputable organizations like the Associated Press or your favorite art gallery's schedule can be considered trusted because while it's possible that an attacker could compromise them, once the attack is detected the organization can find and fix the vulnerability.

For interacting with open source data sources like Wikipedia or OpenStreetMap, you can interact with a snapshot of the data. You can audit this snapshot if you'd like, but for personal use it probably isn't needed. Tracking the live version of the data source (e.g scraping Wikipedia) is unsafe because an attacker could make a change and have it available for minutes or hours before it's noticed and taken down (which is also true of curated data sources run by organizations), but unlike a curated data source there is no vulnerability to plug to shut out the attacker, and so they can continue to attack the assistant until they eventually find a vulnerability. Taking a snapshot and building a personal tool to access that snapshot is an extremely powerful technique.

Some zero leg tools buildable with open source dump + self-hosting:
- Navigation (geocoding with Nominatim, directions with Valhalla, OpenStreetMap data snapshot)
- Wikipedia
- Media search (searchable compendium of titles, authors/contributors, metadata, and informative descriptions for books, movies, tv shows, etc)
- Reference books

Some zero leg tools buildable using 3rd party APIs:
- Weather (NWS API)
- News (Associated Press?)

Untrusted tools:
- Email
- Calendar
- Web

The assistant should be capable of remembering things about the user. While in principle it should be possible for the assistant to update this automatically, in practice it will be most effective when it's curated by the user.

The assistant should be capable of scheduling tasks for in the future. This allows useful functionality like setting timers ("the assistant schedules calling the user in 35 minutes"), or setting reminders.

The assistant should focus on the simple use cases that comprise the vast majority of interactions with external data sources. The assistant can tell you what your credit card bill was last month, but it can't apply for a credit increase. This simplifies implementation, but it also improves user experience because when LLMs attempt to perform complex and failure prone tasks they inevitably fail, and that produces a horrible user experience. It's best for the LLM and the user to each play to their strengths; the LLM handles the 80% of tasks that are basic chores, and the user handles the other 20% of complex tasks that require their personal touch and judgement.

The assistant should require manual user confirmation before performing any sort of write operation by default. User's should be able to configure subsets of operations to not require confirmation, perhaps using some sort of rule system.

Note that it's actually an oversimplication to classify a tool as contributing to certain legs of the trifacta. It's more that *uses* of the tool contribute to trifecta legs. Using the Email tool to send an email doesn't introduce public or private data, while using Email to view emails from known contacts doesn't poison the context with untrusted data (although it could under an aggressive security model). 

Implementing this security model described in this document allows the assistant to access the user's private data in a radically free manner. The assistant can have access to the user's email, calendar, banking information, healthcare data, location data, contacts, and more. This enables use cases like "give me driving directions to Jason's house", or "when's my next gynecologist appointment?", or "how much money did I make last year?", or "When's the kid's next soccer game?"
