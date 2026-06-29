import { Link } from "react-router-dom";
import { Mic2 } from "lucide-react";
import { buttonVariants } from "../ui/button";
import { cn } from "../../lib/utils";

export function PublicNavbar() {
  return (
    <header className="fixed top-6 inset-x-0 z-50 flex justify-center w-full pointer-events-none">
      <div className="container max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 pointer-events-auto">
        <div className="flex h-16 items-center justify-between bg-background/88 backdrop-blur-xl shadow-2xl shadow-black/5 ring-1 ring-border rounded-full px-5 md:px-7">
          <div className="flex items-center gap-6">
            <Link to="/" className="flex items-center gap-2">
              <Mic2 className="h-6 w-6 text-primary" />
              <span className="text-xl font-bold tracking-tight font-heading">Vocalis</span>
            </Link>
            <nav className="hidden md:flex items-center gap-6 text-sm font-medium text-muted-foreground ml-4">
              <a href="#features" className="hover:text-foreground transition-colors">Features</a>
              <a href="#how-it-works" className="hover:text-foreground transition-colors">Workflow</a>
              <a href="#reports" className="hover:text-foreground transition-colors">AI Reports</a>
              <a href="#pricing" className="hover:text-foreground transition-colors">Plans</a>
            </nav>
          </div>
          <div className="flex items-center gap-3">
            <Link to="/auth" className="text-sm font-medium hover:text-foreground/80 transition-colors hidden sm:block">
              Log in
            </Link>
            <Link to="/auth?signup=true" className={cn(buttonVariants({ variant: "default" }), "h-10 rounded-full px-5")}>
              Start
            </Link>
          </div>
        </div>
      </div>
    </header>
  );
}
