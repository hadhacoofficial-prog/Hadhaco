declare module "dompurify" {
  const DOMPurify: {
    sanitize(dirty: string, config?: { ALLOWED_TAGS?: string[]; ALLOWED_ATTR?: string[] }): string;
  };
  export default DOMPurify;
}
