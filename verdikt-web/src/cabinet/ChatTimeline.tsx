import { memo } from 'react';
import { api, fileExt, mapAnalysis, type Message } from '../api/client';
import type { SimilarVerdict } from '../api/types';
import { FileChip } from '../components/FileTile';
import { Icon } from '../components/Icon';
import { fileReadingLabel } from './fileReadingPresentation';
import { Result, Thinking } from './screens';

export type ChatAttachment = Message['attachments'][number];

/** Memoised: the poll skips identical fingerprints, so between stage changes the
 *  whole timeline (including the heavy Result) stays untouched while the timer ticks. */
export const ChatTimeline = memo(function ChatTimeline({messages, onOpen, onOpenVerdict, chatId}: {chatId?: string; messages: Message[]; onOpen: (attachment: ChatAttachment) => void; onOpenVerdict?: (verdict: SimilarVerdict) => void}) {
  return <div className="thread chat-timeline" aria-label="История переписки">
    {messages.map(message => {
      const busy = message.status === 'pending' || message.status === 'running';
      return <section key={message.id} data-message-id={message.id} className={`chat-message chat-message-${message.role}`} aria-label={message.role === 'user' ? 'Ваше сообщение' : 'Ответ помощника'}>
        {message.role === 'user' ? <div className="thread-user"><div className="bubble">
          {message.content && <p className="chat-message-text">{message.content}</p>}
          <div className="chips">{message.attachments.map(a => <div key={a.id}>
            <button type="button" className="document-chip" aria-label={`Открыть ${a.filename}`} onClick={() => onOpen(a)}><FileChip name={a.filename} ext={fileExt(a.filename)} /></button>
            <div className="file-meta">{fileReadingLabel({pages:a.page_count || 0, recognition:a.extraction_status})}</div>
            {chatId && <a className="chat-file-download" href={api.attachmentUrl(chatId,a.id,true)} download={a.filename} aria-label={`Скачать «${a.filename}»`}><Icon name="download" size={14} />Скачать</a>}
          </div>)}</div>
        </div></div> : busy ? <div aria-busy="true"><Thinking stage={message.stage} status={message.status} startedAt={message.created_at} /></div> : message.status === 'failed' ?
          <div className="warn-box" role="alert">{message.error || 'Анализ не выполнен. Отправьте уточнение, чтобы повторить попытку.'}</div> :
          message.result ? <Result a={mapAnalysis(message.result)} onOpenVerdict={onOpenVerdict} /> : <div className="thread-ai chat-message-text">{message.content}</div>}
      </section>;
    })}
  </div>;
});
