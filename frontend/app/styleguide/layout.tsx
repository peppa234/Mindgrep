import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Styleguide · Mindgrep",
  description: "Every token, component state and effect of the Mindgrep design system.",
  robots: { index: false, follow: false },
};

export default function StyleguideLayout({ children }: { children: React.ReactNode }) {
  return children;
}
