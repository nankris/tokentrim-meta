import heapq
def build_order(graph):
    dependencies = {job:set(values) for job,values in graph.items()}
    nodes = set(dependencies).union(*(values for values in dependencies.values()))
    followers = {job:set() for job in nodes}
    pending = {job:len(dependencies.get(job,())) for job in nodes}
    for job, values in dependencies.items():
        for dependency in values: followers[dependency].add(job)
    ready = [job for job in nodes if pending[job] == 0]
    heapq.heapify(ready)
    result = []
    while ready:
        job = heapq.heappop(ready)
        result.append(job)
        for follower in followers[job]:
            pending[follower] -= 1
            if pending[follower] == 0: heapq.heappush(ready,follower)
    if len(result) != len(nodes): raise ValueError('dependency cycle')
    return result
def job_count(graph):
    return len(set(graph).union(*(set(v) for v in graph.values())))
