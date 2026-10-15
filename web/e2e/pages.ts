/** The 11 pages (SPEC 16.1) and the prototype artboard each one follows. */
export interface StudioPage {
  id: string;
  path: string;
  prototype: string;
}

export const PAGES: StudioPage[] = [
  { id: "setup", path: "/setup", prototype: "Setup" },
  { id: "spec", path: "/s/demo/spec", prototype: "Spec" },
  { id: "novel", path: "/s/demo/e/1/novel", prototype: "Main" },
  { id: "script", path: "/s/demo/e/1/script", prototype: "Script" },
  { id: "assets", path: "/s/demo/e/1/assets", prototype: "Assets" },
  { id: "storyboard", path: "/s/demo/e/1/storyboard", prototype: "Storyboard" },
  { id: "generate", path: "/s/demo/e/1/generate", prototype: "Generate" },
  { id: "post", path: "/s/demo/e/1/post", prototype: "Post" },
  { id: "models", path: "/models", prototype: "Models" },
  { id: "sync", path: "/s/demo/sync", prototype: "Sync" },
  { id: "dashboard", path: "/s/demo/dashboard", prototype: "Dashboard" },
];
