import * as React from "react";
import { cn } from "@/lib/utils";
import { type LucideIcon, ArrowUpRight, ArrowDownRight } from "lucide-react";

// Standard shadcn/ui Card primitives
const Card = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        "rounded-xl border border-border bg-card text-card-foreground shadow-xs transition-all",
        className
      )}
      {...props}
    />
  )
);
Card.displayName = "Card";

const CardHeader = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("flex flex-col space-y-1.5 p-6", className)} {...props} />
  )
);
CardHeader.displayName = "CardHeader";

const CardTitle = React.forwardRef<HTMLHeadingElement, React.HTMLAttributes<HTMLHeadingElement>>(
  ({ className, ...props }, ref) => (
    <h3 ref={ref} className={cn("font-semibold leading-none tracking-tight text-lg", className)} {...props} />
  )
);
CardTitle.displayName = "CardTitle";

const CardDescription = React.forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLParagraphElement>>(
  ({ className, ...props }, ref) => (
    <p ref={ref} className={cn("text-sm text-muted-foreground", className)} {...props} />
  )
);
CardDescription.displayName = "CardDescription";

const CardContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("p-6 pt-0", className)} {...props} />
  )
);
CardContent.displayName = "CardContent";

const CardFooter = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("flex items-center p-6 pt-0", className)} {...props} />
  )
);
CardFooter.displayName = "CardFooter";

// Specialized Premium wrappers (API compatible with standard custom designs)
interface FeatureCardProps extends React.ComponentPropsWithoutRef<typeof Card> {
  icon: LucideIcon;
  title: string;
  description: string;
}

const FeatureCard = React.forwardRef<HTMLDivElement, FeatureCardProps>(
  ({ className, icon: Icon, title, description, ...props }, ref) => {
    return (
      <Card ref={ref} className={cn("group hover:border-violet-500/50 hover:shadow-md", className)} {...props}>
        <CardHeader>
          <div className="flex size-10 items-center justify-center rounded-lg bg-violet-500/10 text-violet-600 dark:bg-violet-500/20 dark:text-violet-400 mb-2 transition-transform group-hover:scale-105">
            <Icon className="size-5" />
          </div>
          <CardTitle className="group-hover:text-violet-600 dark:group-hover:text-violet-400 transition-colors">{title}</CardTitle>
          <CardDescription className="pt-1.5">{description}</CardDescription>
        </CardHeader>
      </Card>
    );
  }
);
FeatureCard.displayName = "FeatureCard";

interface InfoCardProps extends React.ComponentPropsWithoutRef<typeof Card> {
  title: string;
  description?: string;
  action?: React.ReactNode;
}

const InfoCard = React.forwardRef<HTMLDivElement, InfoCardProps>(
  ({ className, title, description, action, children, ...props }, ref) => {
    return (
      <Card ref={ref} className={cn(className)} {...props}>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
          <div className="space-y-1">
            <CardTitle>{title}</CardTitle>
            {description && <CardDescription>{description}</CardDescription>}
          </div>
          {action && <div>{action}</div>}
        </CardHeader>
        <CardContent>{children}</CardContent>
      </Card>
    );
  }
);
InfoCard.displayName = "InfoCard";

interface StatisticsCardProps extends React.ComponentPropsWithoutRef<typeof Card> {
  title: string;
  value: string | number;
  change?: string | number;
  trend?: "up" | "down";
  icon?: LucideIcon;
}

const StatisticsCard = React.forwardRef<HTMLDivElement, StatisticsCardProps>(
  ({ className, title, value, change, trend, icon: Icon, ...props }, ref) => {
    return (
      <Card ref={ref} className={cn("hover:shadow-xs", className)} {...props}>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardDescription className="font-medium text-xs uppercase tracking-wider">{title}</CardDescription>
          {Icon && <Icon className="size-4 text-muted-foreground" />}
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{value}</div>
          {change && (
            <div className="flex items-center gap-1 mt-1 text-xs">
              {trend === "up" ? (
                <span className="flex items-center text-emerald-600 dark:text-emerald-400">
                  <ArrowUpRight className="size-3" /> {change}
                </span>
              ) : (
                <span className="flex items-center text-red-600 dark:text-red-400">
                  <ArrowDownRight className="size-3" /> {change}
                </span>
              )}
              <span className="text-muted-foreground">vs last week</span>
            </div>
          )}
        </CardContent>
      </Card>
    );
  }
);
StatisticsCard.displayName = "StatisticsCard";

interface StatusCardProps extends React.ComponentPropsWithoutRef<typeof Card> {
  status: "success" | "warning" | "error" | "info";
  title: string;
  message: string;
}

const StatusCard = React.forwardRef<HTMLDivElement, StatusCardProps>(
  ({ className, status, title, message, ...props }, ref) => {
    const statusMap = {
      success: "border-emerald-500/20 bg-emerald-500/5 text-emerald-800 dark:text-emerald-400",
      warning: "border-amber-500/20 bg-amber-500/5 text-amber-800 dark:text-amber-400",
      error: "border-red-500/20 bg-red-500/5 text-red-800 dark:text-red-400",
      info: "border-blue-500/20 bg-blue-500/5 text-blue-800 dark:text-blue-400",
    };

    const indicatorMap = {
      success: "bg-emerald-500",
      warning: "bg-amber-500",
      error: "bg-red-500",
      info: "bg-blue-500",
    };

    return (
      <Card ref={ref} className={cn("border border-dashed", statusMap[status], className)} {...props}>
        <CardHeader className="p-4 flex flex-row items-start gap-3 space-y-0">
          <span className={cn("size-2 rounded-full mt-1.5 shrink-0", indicatorMap[status])} />
          <div>
            <h4 className="font-semibold text-sm">{title}</h4>
            <p className="text-xs mt-0.5 opacity-90 leading-normal">{message}</p>
          </div>
        </CardHeader>
      </Card>
    );
  }
);
StatusCard.displayName = "StatusCard";

export {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
  FeatureCard,
  InfoCard,
  StatisticsCard,
  StatusCard,
};
