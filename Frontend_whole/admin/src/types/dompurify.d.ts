declare module "dompurify" {
  interface DOMPurifyConfig {
    ALLOWED_TAGS?: string[];
    ALLOWED_ATTR?: string[];
    FORBID_TAGS?: string[];
    FORBID_ATTR?: string[];
    USE_PROFILES?: { html?: boolean; svg?: boolean; svgFilters?: boolean; mathMl?: boolean };
  }
  const DOMPurify: {
    sanitize(dirty: string, config?: DOMPurifyConfig): string;
  };
  export default DOMPurify;
}
