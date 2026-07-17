/// <reference types="vite/client" />

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

// Axios custom config
import 'axios';

declare module 'axios' {
  interface AxiosRequestConfig {
    skipErrorLog?: boolean;
  }
}

// Global Vite env reference
declare global {
  // eslint-disable-next-line no-var
  var __VITE_ENV__: Record<string, string> | undefined;
}
