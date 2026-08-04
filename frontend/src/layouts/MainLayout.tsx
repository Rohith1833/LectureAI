import { Outlet } from "react-router-dom";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import Sidebar from "@/components/Sidebar";
import { Breadcrumb } from "@/components/ui/breadcrumb";

export default function MainLayout() {
  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground transition-colors duration-200">
      <Navbar />
      <div className="flex flex-1 w-full">
        <Sidebar />
        <main className="flex-1 w-full flex flex-col p-4 sm:p-6 lg:p-8">
          <div className="mx-auto w-full max-w-6xl flex-1 flex flex-col">
            <Breadcrumb />
            <div className="flex-1">
              <Outlet />
            </div>
          </div>
        </main>
      </div>
      <Footer />
    </div>
  );
}
