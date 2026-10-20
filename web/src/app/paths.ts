/** Route paths (SPEC 16.1). Until M1 creates real series, links point at the demo project. */

export const DEMO_SERIES = "demo";
export const DEMO_EPISODE = "1";

export const STEPS = ["novel", "script", "assets", "storyboard", "generate", "post"] as const;
export type Step = (typeof STEPS)[number];

export const paths = {
  setup: () => "/setup",
  models: () => "/models",
  spec: (series: string) => `/s/${series}/spec`,
  sync: (series: string) => `/s/${series}/sync`,
  dashboard: (series: string) => `/s/${series}/dashboard`,
  step: (series: string, episode: string, step: Step) => `/s/${series}/e/${episode}/${step}`,
  devJobs: () => "/dev/jobs",
  devComponents: () => "/dev/components",
};
