import { Nav } from "@/components/nav";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Nav />
      <main id="main" className="mx-auto max-w-6xl px-4 pt-8 pb-16 sm:px-6">
        {children}
      </main>
    </>
  );
}
