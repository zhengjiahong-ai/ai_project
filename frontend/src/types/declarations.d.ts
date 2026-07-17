// CSS module declarations
declare module '*.css' {
  const content: Record<string, string>;
  export default content;
}

// Vite URL imports
declare module '*.js?url' {
  const url: string;
  export default url;
}

declare module '*.min.js?url' {
  const url: string;
  export default url;
}
