# @Author : guopeiming
# @Datetime : 2019/10/16 14:17
# @File : dataset.py
# @Last Modify Time : 2019/10/18 08:33
# @Contact : 1072671422@qq.com, guopeiming2016@{gmail.com, 163.com}
import torch
import torch.nn as nn
import torch.nn.init as init
from config import Constants


class CharEncoder(nn.Module):
    """
    submodel of NNTransSegmentor ------ CharEncoder
    """
    def __init__(self, pretra_char_embed, char_embed_num, char_embed_dim, char_embed_dim_no_static, char_embed_max_norm,
                 pretra_bichar_embed, bichar_embed_num, bichar_embed_dim, bichar_embed_dim_no_static,
                 bichar_embed_max_norm, dropout_embed, encoder_embed_dim, dropout_encoder_embed, encoder_lstm_hid_size,
                 dropout_encoder_hid, device):
        super(CharEncoder, self).__init__()

        assert pretra_char_embed.shape[0] == char_embed_num and \
            pretra_char_embed.shape[1] == char_embed_dim and \
            pretra_bichar_embed.shape[0] == bichar_embed_num and \
            pretra_bichar_embed.shape[1] == bichar_embed_dim, 'pretrained embeddings shape error.'

        self.char_embeddings_static = nn.Embedding.from_pretrained(pretra_char_embed, True, Constants.padId, char_embed_max_norm)
        self.char_embeddings_no_static = nn.Embedding(char_embed_num, char_embed_dim_no_static, Constants.padId, char_embed_max_norm)

        self.bichar_embeddings_static = nn.Embedding.from_pretrained(pretra_bichar_embed, True, Constants.padId, bichar_embed_max_norm)
        self.bichar_embeddings_no_static = nn.Embedding(bichar_embed_num, bichar_embed_dim_no_static, Constants.padId, bichar_embed_max_norm)

        self.dropout_embed_layer = nn.Dropout(dropout_embed)

        self.embed_compose_l = nn.Sequential(
            nn.Linear(char_embed_dim+char_embed_dim_no_static+bichar_embed_dim+bichar_embed_dim_no_static, encoder_embed_dim, bias=True),
            nn.Tanh()
        )
        self.embed_compose_r = nn.Sequential(
            nn.Linear(char_embed_dim+char_embed_dim_no_static+bichar_embed_dim+bichar_embed_dim_no_static, encoder_embed_dim, bias=True),
            nn.Tanh()
        )

        self.dropout_encoder_embed_layer = nn.Dropout(dropout_encoder_embed)

        self.lstm_l = nn.LSTMCell(encoder_embed_dim, encoder_lstm_hid_size, bias=True)
        self.lstm_r = nn.LSTMCell(encoder_embed_dim, encoder_lstm_hid_size, bias=True)

        self.dropout_encoder_hid_layer = nn.Dropout(dropout_encoder_hid)

        self.dropout_embed = 1
        self.dropout_encoder_embed = 1
        self.dropout_encoder_hid = 1
        self.encoder_lstm_hid_size = encoder_lstm_hid_size
        self.device = device

        self.__init_para()

    def forward(self, insts):
        insts_char, insts_bichar_l, insts_bichar_r = insts[0], insts[1], insts[2]  # (batch_size, seq_len)
        batch_size, seq_len = insts_char.shape[0], insts_char.shape[1]

        char_embeddings = self.char_embeddings_static(insts_char).permute(1, 0, 2)  # (seq_len, batch_size, embed_size)
        char_embeddings_no_static = self.char_embeddings_no_static(insts_char).permute(1, 0, 2)
        bichar_embeddings_l = self.bichar_embeddings_static(insts_bichar_l).permute(1, 0, 2)
        bichar_embeddings_l_no_static = self.bichar_embeddings_no_static(insts_bichar_l).permute(1, 0, 2)
        bichar_embeddings_r = self.bichar_embeddings_static(insts_bichar_r).permute(1, 0, 2)
        bichar_embeddings_r_no_static = self.bichar_embeddings_no_static(insts_bichar_r).permute(1, 0, 2)

        if self.training:
            char_embeddings = self.dropout_embed_layer(torch.cat([char_embeddings, char_embeddings_no_static], 2))
            bichar_embeddings_l = self.dropout_embed_layer(torch.cat([bichar_embeddings_l, bichar_embeddings_l_no_static], 2))
            bichar_embeddings_r = self.dropout_embed_layer(torch.cat([bichar_embeddings_r, bichar_embeddings_r_no_static], 2))
        else:
            char_embeddings = self.dropout_embed*torch.cat([char_embeddings, char_embeddings_no_static], 2)
            bichar_embeddings_l = self.dropout_embed*torch.cat([bichar_embeddings_l, bichar_embeddings_l_no_static], 2)
            bichar_embeddings_r = self.dropout_embed*torch.cat([bichar_embeddings_r, bichar_embeddings_r_no_static], 2)

        # (seq_len, batch_size, encoder_embed_dim)
        embeddins_l = self.embed_compose_l(torch.cat([char_embeddings, bichar_embeddings_l], 2))
        embeddins_r = self.embed_compose_r(torch.cat([char_embeddings, bichar_embeddings_r], 2))
        if self.training:
            embeddins_l = self.dropout_encoder_embed_layer(embeddins_l)
            embeddins_r = self.dropout_encoder_embed_layer(embeddins_r)
        else:
            embeddins_l = self.dropout_encoder_embed * embeddins_l
            embeddins_r = self.dropout_encoder_embed * embeddins_r

        h_l, c_l, h_r, c_r = list(map(lambda x: x.squeeze(0).to(self.device), torch.zeros((4, batch_size, self.encoder_lstm_hid_size)).chunk(4, 0)))
        lstm_l_hid, lstm_r_hid = [], []
        for step in range(seq_len):
            h_l, c_l = self.lstm_l(embeddins_l[step], (h_l, c_l))  # (batch_size, encoder_lstm_hid_size)
            h_r, c_r = self.lstm_r(embeddins_r[seq_len - 1 - step], (h_r, c_r))

            if self.training:
                # (1, batch_size, encoder_lstm_hid_size)
                lstm_l_hid.append(self.dropout_encoder_hid_layer(h_l).unsqueeze(0))
                lstm_r_hid.append(self.dropout_encoder_hid_layer(h_r).unsqueeze(0))
            else:
                # (1, batch_size, encoder_lstm_hid_size)
                lstm_l_hid.append((self.dropout_encoder_hid*h_l).unsqueeze(0))
                lstm_r_hid.append((self.dropout_encoder_hid*h_r).unsqueeze(0))

        encoder_out = [torch.cat([lstm_l_hid[i], lstm_r_hid[seq_len-i-1]], 2) for i in range(seq_len)]
        return torch.cat(encoder_out, 0)  # (seq_len, batch_size, encoder_lstm_hid_size*2)

    def __init_para(self):
        init.xavier_uniform_(self.char_embeddings_no_static.weight)
        init.xavier_uniform_(self.bichar_embeddings_no_static.weight)
        init.xavier_uniform_(self.lstm_l.weight_ih)
        init.xavier_uniform_(self.lstm_l.weight_hh)
        init.xavier_uniform_(self.lstm_r.weight_ih)
        init.xavier_uniform_(self.lstm_r.weight_hh)
        init.uniform_(self.lstm_l.bias_ih)
        init.uniform_(self.lstm_l.bias_hh)
        init.uniform_(self.lstm_r.bias_ih)
        init.uniform_(self.lstm_r.bias_hh)
        init.xavier_uniform_(self.embed_compose_l[0].weight)
        init.xavier_uniform_(self.embed_compose_r[0].weight)
        init.uniform_(self.embed_compose_l[0].bias)
        init.uniform_(self.embed_compose_r[0].bias)
        self.char_embeddings_no_static.weight.requires_grad_(True)
        self.bichar_embeddings_no_static.weight.requires_grad_(True)

