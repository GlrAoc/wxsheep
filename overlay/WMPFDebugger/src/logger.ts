import { CliOptions } from "./cli";
import * as fs from "node:fs";
import { inspect } from "node:util";

type Logger = {
    info: (...messages: unknown[]) => void;
    error: (...messages: unknown[]) => void;
    main_debug: (...messages: unknown[]) => void;
    frida_debug: (...messages: unknown[]) => void;
};

/**
 * 可选的文件日志（由 MINIAPP_PROXY_LOG 指定路径）。
 *
 * 为什么需要它：外部脚本用 detached 方式拉起本代理时，Node 在 Windows 上
 * 无法把子进程的 stdout 句柄写进父进程打开的文件（实测日志恒为 0 字节），
 * 所以改由代理进程自己打开文件写一份。外部脚本据此判断"注入到了哪个 pid"。
 */
const logPath = process.env.MINIAPP_PROXY_LOG;
let stream: fs.WriteStream | null = null;

const stamp = () => new Date().toTimeString().slice(0, 8);
const fmt = (m: unknown) =>
    typeof m === "string"
        ? m
        : m instanceof Error
            ? m.stack || m.message
            : inspect(m, { breakLength: Infinity, depth: 4 });

const writeLine = (line: string) => {
    if (!stream) return;
    try {
        stream.write(line + "\n");
    } catch {
        /* 日志写失败不能影响主流程 */
    }
};

if (logPath) {
    try {
        stream = fs.createWriteStream(logPath, { flags: "a" });
        stream.on("error", () => {
            stream = null;
        });
        writeLine(`[logger] proxy log opened pid=${process.pid} at ${new Date().toISOString()}`);
        process.on("exit", (code) => {
            writeLine(`[logger] proxy exit code=${code} at ${new Date().toISOString()}`);
        });
    } catch {
        stream = null;
    }

    // 第三方模块（RemoteDebugUtils 等）直接用 console，这里统一兜住
    const origLog = console.log.bind(console);
    const origErr = console.error.bind(console);
    console.log = (...a: unknown[]) => {
        origLog(...a);
        writeLine(`${stamp()} ${a.map(fmt).join(" ")}`);
    };
    console.error = (...a: unknown[]) => {
        origErr(...a);
        writeLine(`${stamp()} [stderr] ${a.map(fmt).join(" ")}`);
    };
}

const create_logger = (options: CliOptions): Logger => ({
    info: (...messages) => {
        console.log(...messages);
    },
    error: (...messages) => {
        console.error(...messages);
    },
    main_debug: (...messages) => {
        if (options.debugMain) {
            console.log(...messages);
        }
    },
    frida_debug: (...messages) => {
        if (options.debugFrida) {
            console.log(...messages);
        }
    },
});

export { Logger, create_logger };
