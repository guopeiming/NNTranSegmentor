# @Author : guopeiming
# @Datetime : 2019/10/12 18:18
# @File : train.py
# @Last Modify Time : 2019/10/18 08:33
# @Contact : 1072671422@qq.com, guopeiming2016@{gmail.com, 163.com}
import os
import sys
import torch
import argparse
from config import Constants
from utils.optim import Optim
from config.config import MyConf
from utils.data_utils import load_data
from utils.visualLogger import VisualLogger
from model.ParaNNTranSegmentor import ParaNNTranSegmentor


def parse_args():
    parser = argparse.ArgumentParser(description="NNTranSegmentor")
    parser.add_argument("--config", dest="config", type=str, required=False, default="./config/config.cfg",
                        help="path of config_file")
    args = parser.parse_args()
    config = MyConf(args.config)
    return config


def cal_preformance(pred, golds, criterion, device):
    batch_size, seq_len = golds.shape[0], golds.shape[1]
    golds_last_seg_idx = torch.tensor([seq_len]*batch_size, dtype=torch.long).to(device)
    pred_last_seg_idx = torch.tensor([seq_len]*batch_size, dtype=torch.long).to(device)
    pred_label = torch.argmax(pred, 2)
    seg_word, char, cor_char, pred_word, golds_word = 0, 0, 0, 0, 0
    for idx in range(seq_len-1, -1, -1):
        pred_seg_mask = pred_label[:, idx] == Constants.SEP
        golds_seg_mask = golds[:, idx] == Constants.SEP
        no_pad_mask = golds[:, idx] != Constants.actionPadId
        seg_word += torch.sum((pred_last_seg_idx == golds_last_seg_idx)[pred_seg_mask * golds_seg_mask]).item()
        pred_last_seg_idx[pred_seg_mask*no_pad_mask] = idx
        golds_last_seg_idx[golds_seg_mask*no_pad_mask] = idx

        char += torch.sum(no_pad_mask).item()
        cor_char += torch.sum((golds[:, idx] - pred_label[:, idx]) == 0).item()
        pred_word += torch.sum(pred_label[:, idx][no_pad_mask] == Constants.SEP).item()
        golds_word += torch.sum(golds[:, idx] == Constants.SEP).item()
        assert seg_word <= pred_word and seg_word <= golds_word, 'evaluation criteria wrong.'

    mask = golds != Constants.actionPadId
    pred, golds = torch.masked_select(pred, mask.unsqueeze(2)).view(-1, 2), torch.masked_select(golds, mask)  # [seq_len_sum, 2/1]
    assert golds.shape[0] == pred.shape[0], 'golds and pred\'s shape are different.'

    loss = criterion(pred, golds)

    return loss, golds_word, pred_word, seg_word, char, cor_char


def eval_model(model, criterion, dev_data, test_data, device):
    model.eval()
    print('Validation starts...')
    eval_dataset(model, criterion, dev_data, device, 'dev')
    eval_dataset(model, criterion, test_data, device, 'test')
    print('Validation ends.')


def eval_dataset(model, criterion, data, device, typ):
    total_loss, golds_words, pred_words, seg_words, chars, cor_chars = 0.0, 0, 0, 0, 0, 0
    for batch, golds in data:
        batch = batch.to(device)
        golds = golds.to(device)

        pred = model(batch)
        loss, golds_word, pred_word, seg_word, char, cor_char = cal_preformance(pred, golds, criterion, device)
        total_loss += loss.item()
        golds_words += golds_word
        pred_words += pred_word
        seg_words += seg_word
        chars += char
        cor_chars += cor_char
    avg_loss = total_loss/chars
    P = seg_words/pred_words
    R = seg_words/golds_words
    F = (2*P*R)/(P+R)
    ACC = cor_chars/chars
    print('Model performance in %s dataset Loss: %.05f, F: %.05f, P: %.05f, R: %.05f, ACC: %.05f' %
          (typ, avg_loss, F, P, R, ACC))


def main():
    config = parse_args()

    # ========= Loading Dataset ========= #
    print(config)
    print("Loading dataset starts...")
    train_data, dev_data, test_data, train_dataset = load_data(config)
    print('\n\n', end='')

    # ========= Preparing Model ========= #
    print("Preparing Model starts...")
    if config.use_cuda and torch.cuda.is_available():
        config.device = torch.device('cuda:0')
        print('You will train model in cuda: %d.\n' % config.device.index)
    else:
        config.device = torch.device('cpu')
        print('GPU is not available, use CPU default.\n')
    model = ParaNNTranSegmentor(train_dataset.get_id2char(),
                                train_dataset.get_word2id(),
                                train_dataset.get_char_vocab_size(),
                                train_dataset.get_word_vocab_size(),
                                config)
    if config.use_cuda:
        model.to(config.device)
    print(model, end='\n\n\n')

    criterion = torch.nn.CrossEntropyLoss(reduction='sum').to(config.device)
    optimizer = Optim(config.opti_name, config.learning_rate, config.weight_decay, model)
    visual_logger = VisualLogger(config.visual_logger_path)

    # ========= Training ========= #
    print('Training starts...')
    total_loss, golds_words, pred_words, seg_words, chars, cor_chars = 0.0, 0, 0, 0, 0, 0
    for epoch_i in range(config.epoch):
        for batch_i, (batch, golds) in enumerate(train_data):
            batch = batch.to(config.device)
            golds = golds.to(config.device)
            model.train()

            optimizer.zero_grad()
            pred = model(batch, golds)
            loss, golds_word, pred_word, seg_word, char, cor_char = cal_preformance(pred, golds, criterion, config.device)
            total_loss += loss.item()
            golds_words += golds_word
            pred_words += pred_word
            seg_words += seg_word
            chars += char
            cor_chars += cor_char

            loss.backward()
            optimizer.step()

            if (batch_i+1+epoch_i*(len(train_data))) % config.logInterval == 0:
                avg_loss = total_loss/chars
                ACC = cor_chars/chars
                P = seg_words/pred_words
                R = seg_words/golds_words
                F = (2*P*R)/(P+R)
                print('[%d/%d], [%d/%d] Loss: %.05f, F: %.05f, P: %.05f, R: %.05f, ACC: %.05f' %
                      (epoch_i+1, config.epoch, batch_i+1, len(train_data), avg_loss, F, P, R, ACC))
                sys.stdout.flush()
                scal = {'Loss': avg_loss, 'F': F, 'P': P, 'R': R, 'ACC': ACC}
                visual_logger.visual_scalars(scal, batch_i+1+epoch_i*(len(train_data)))
                total_loss, golds_words, pred_words, seg_words, chars, cor_chars = 0.0, 0, 0, 0, 0, 0
                # break
            if (batch_i+1+epoch_i*(len(train_data))) % config.valInterval == 0:
                eval_model(model, criterion, dev_data, test_data, config.device)
                sys.stdout.flush()
            if (batch_i+1+epoch_i*(len(train_data))) % config.saveInterval == 0:
                if not os.path.exists(config.save_path):
                    os.mkdir(config.save_path)
                filename = '%d.model' % (batch_i+1+epoch_i*len(train_data))
                modelpath = os.path.join(config.save_path, filename)
                torch.save(model, modelpath)
    visual_logger.close()
    print('Training ends.')


if __name__ == '__main__':
    main()

