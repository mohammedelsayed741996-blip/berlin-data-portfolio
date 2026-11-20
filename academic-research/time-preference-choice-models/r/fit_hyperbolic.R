# Replicates the core analysis in base R, without extra packages:
# the pre-registered exclusions, a penalised maximum-likelihood hyperbolic fit per participant,
# and the framing effect on log k.
#
# Usage (from the project folder):  Rscript r/fit_hyperbolic.R data outputs/hyperbolic_fits_r.csv
# scripts/compare_r_python.py then checks the estimates against the Python version.

args <- commandArgs(trailingOnly = TRUE)
data_dir <- if (length(args) >= 1) args[1] else "data"
out_file <- if (length(args) >= 2) args[2] else "outputs/hyperbolic_fits_r.csv"

tr <- read.csv(gzfile(file.path(data_dir, "trials.csv.gz")), stringsAsFactors = FALSE)
tr$catch <- tr$catch %in% c(TRUE, "True", "TRUE", "true")

# Q1: keep each participant's first submission
tr <- tr[tr$submission == 1, ]
# Q2: two or more of four catch trials failed; Q3: median response time under 450 ms
fails <- tapply(tr$choice_ll[tr$catch], tr$pid[tr$catch], sum)
med_rt <- tapply(tr$rt_ms, tr$pid, median)
excluded <- union(names(fails)[fails >= 2], names(med_rt)[med_rt < 450])
d <- tr[!tr$catch & !(tr$pid %in% excluded), ]
cat(sprintf("Participants analysed: %d (excluded %d)\n", length(unique(d$pid)), length(excluded)))

prior_mean <- c(log(0.01), log(0.3))
prior_sd <- c(2.5, 1.5)

penalised_nll <- function(th, xs, ts, xl, tl, y) {
  k <- exp(th[1])
  tau <- exp(th[2])
  z <- tau * (xl / (1 + k * tl) - xs / (1 + k * ts))
  z <- pmin(pmax(z, -35), 35)
  p <- 1 / (1 + exp(-z))
  p <- pmin(pmax(p, 1e-6), 1 - 1e-6)
  -sum(y * log(p) + (1 - y) * log(1 - p)) + 0.5 * sum(((th - prior_mean) / prior_sd)^2)
}

fit_one <- function(g) {
  starts <- list(c(log(0.01), log(0.3)), c(log(0.1), log(0.1)))
  best <- NULL
  for (s in starts) {
    r <- optim(s, penalised_nll, xs = g$ss_amount, ts = g$ss_delay, xl = g$ll_amount, tl = g$ll_delay,
               y = g$choice_ll, method = "L-BFGS-B", lower = c(-12, -8), upper = c(2, 4))
    if (is.null(best) || r$value < best$value) best <- r
  }
  data.frame(pid = g$pid[1], frame = g$frame[1], log_k = best$par[1], log_tau = best$par[2])
}

fits <- do.call(rbind, lapply(split(d, d$pid), fit_one))
dir.create(dirname(out_file), showWarnings = FALSE, recursive = TRUE)
write.csv(fits, out_file, row.names = FALSE)

# Framing effect on log k: date minus delay
m_date <- mean(fits$log_k[fits$frame == "date"])
m_delay <- mean(fits$log_k[fits$frame == "delay"])
tt <- t.test(log_k ~ frame, data = fits)
wt <- wilcox.test(log_k ~ frame, data = fits)
cat(sprintf("Mean log k: date %.3f, delay %.3f, difference %.3f\n", m_date, m_delay, m_date - m_delay))
cat(sprintf("Welch t = %.2f, df = %.1f, p = %.2g; 95%% CI %.3f to %.3f\n",
            tt$statistic, tt$parameter, tt$p.value, tt$conf.int[1], tt$conf.int[2]))
cat(sprintf("Wilcoxon rank-sum p = %.2g\n", wt$p.value))
