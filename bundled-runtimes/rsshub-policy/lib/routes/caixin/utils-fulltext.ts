import crypto from 'node:crypto';

import { hextob64, KJUR } from 'jsrsasign';

import { config } from '@/config';
import ofetch from '@/utils/ofetch';

const rsaPrivateKey = process.env.CAIXIN_RSA_PRIVATE_KEY?.replaceAll('\\n', '\n');

export async function getFulltext(url: string) {
    if (!config.caixin.cookie || !rsaPrivateKey) {
        return;
    }
    if (!/\d+\.html/.test(url)) {
        return;
    }
    const articleID = url.match(/(\d+)\.html/)![1];

    const nonce = crypto.randomUUID().replaceAll('-', '').toUpperCase();

    const userID = config.caixin.cookie
        .split(';')
        .find((e) => e.includes('SA_USER_UID'))
        ?.split('=', 2)[1];

    const rawString = `id=${articleID}&uid=${userID}&${nonce}=nonce`;

    const sig = new KJUR.crypto.Signature({ alg: 'SHA256withRSA' });
    sig.init(rsaPrivateKey);
    sig.updateString(rawString);
    const sigValueHex = hextob64(sig.sign());

    const isWeekly = url.includes('weekly');
    const res = await ofetch('https://gateway.caixin.com/api/newauth/checkAuthByIdJsonp', {
        query: {
            type: 1,
            page: isWeekly ? 0 : 1,
            rand: Math.random(),
            id: articleID,
        },
        headers: {
            'X-Sign': encodeURIComponent(sigValueHex),
            'X-Nonce': encodeURIComponent(nonce),
            Cookie: config.caixin.cookie,
        },
    });

    const { content = '', pictureList } = JSON.parse(res.data.match(/resetContentInfo\((.*)\)/)[1]);
    return content + (pictureList ? pictureList.map((e) => `<img src="${e.url}" id="picture_${e.id}" alt="${e.desc}"><dl><dt>${e.desc}</dt></dl>`).join('') : '');
}
