import { createContext, useContext } from "react";

export type Notice = { message: string; tone: "success" | "error" };
export const ToastContext = createContext<
  (message: string, tone?: Notice["tone"]) => void
>(() => undefined);
export function useToast() {
  return useContext(ToastContext);
}
