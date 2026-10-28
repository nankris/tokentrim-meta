def build_order(graph):
    result = []
    def visit(job):
        if job in result: return
        for dependency in graph.get(job, []): visit(dependency)
        result.append(job)
    for job in graph: visit(job)
    return result
def job_count(graph):
    return len(set(graph).union(*(set(v) for v in graph.values())))
