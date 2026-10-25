declare module "*.css" {}
declare module "*.svg" {
  const url: string;
  export default url;
}
declare module "*.png" {
  const url: string;
  export default url;
}
declare module "*.jpg" {
  const url: string;
  export default url;
}
declare module "*.jpeg" {
  const url: string;
  export default url;
}
declare module "*.webp" {
  const url: string;
  export default url;
}
declare module "*.gif" {
  const url: string;
  export default url;
}
declare module "*.mdx" {
  import type { ComponentType } from "react";

  const Content: ComponentType;
  export default Content;
}
