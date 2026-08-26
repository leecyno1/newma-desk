import path from 'node:path';

import winston from 'winston';

import { config } from '@/config';

let transports: Array<typeof winston.transports.File> = [];
if (!config.noLogfiles && !process.env.VERCEL) {
    transports = [
        new winston.transports.File({
            filename: path.resolve('logs/error.log'),
            level: 'error',
            maxsize: 10 * 1024 * 1024,
            maxFiles: 3,
            tailable: true,
        }),
        new winston.transports.File({
            filename: path.resolve('logs/combined.log'),
            maxsize: 25 * 1024 * 1024,
            maxFiles: 5,
            tailable: true,
        }),
    ];
}
const logger = winston.createLogger({
    level: config.loggerLevel,
    format: winston.format.combine(
        winston.format.timestamp({ format: 'YYYY-MM-DD HH:mm:ss.SSS' }),
        winston.format.printf((info) =>
            JSON.stringify({
                timestamp: info.timestamp,
                level: info.level,
                message: info.message,
            })
        )
    ),
    transports,
    exitOnError: true,
});

for (const transport of transports) {
    transport.on('error', (error) => {
        try {
            process.stderr.write('RSSHub log transport error: ' + (error instanceof Error ? error.message : String(error)) + '\n');
        } catch {
            // stderr may be unavailable during process teardown.
        }
    });
}

//
// If we're not in production then log to the `console` with the format:
// `${info.level}: ${info.message} JSON.stringify({ ...rest }) `
//
if (!config.isPackage) {
    logger.add(
        new winston.transports.Console({
            format: winston.format.printf((info) => {
                const infoLevel = winston.format.colorize().colorize(info.level, config.showLoggerTimestamp ? `[${info.timestamp}] ${info.level}` : info.level);
                return `${infoLevel}: ${info.message}`;
            }),
            silent: process.env.NODE_ENV === 'test',
        })
    );
}

export default logger;
