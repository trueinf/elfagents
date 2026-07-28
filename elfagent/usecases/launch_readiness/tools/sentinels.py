"""Why these tools never return null for "nothing on file".

An absent row and a row saying "no restriction applies" mean different things,
and a regulatory agent that cannot tell them apart is dangerous. If a tool
returned None, the model would have to infer meaning from silence — and
silence-means-permitted is precisely the inference we cannot afford it to make.

So every tool returns a populated object with an explicit status. The agent
weighs "no record" as its own state, and the trace shows it did.
"""

NO_RECORD = "no_record"
