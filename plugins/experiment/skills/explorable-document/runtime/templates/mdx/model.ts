export function queue(
  arrival: number,
  service: number,
): { utilization: number; jobs: number | null } {
  const utilization = arrival / service;
  return {
    utilization,
    jobs: utilization >= 1 ? null : utilization / (1 - utilization),
  };
}
