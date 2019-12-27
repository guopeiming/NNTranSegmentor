# @Author : guopeiming
# @Datetime : 2019/12/09 15:18
# @File : bert_utils.py
# @Last Modify Time : 2019/12/09 15:18
# @Contact : guopeiming2016@{qq, gmail, 163}.com
import torch
from config import Constants
from torch.utils.data import Dataset, DataLoader


class CWSBertDataset(Dataset):
    def __init__(self, insts, golds):
        super(CWSBertDataset, self).__init__()
        self.insts = insts
        self.golds = golds

    def __len__(self):
        return len(self.insts)

    def __getitem__(self, idx):
        return [self.insts[idx], self.golds[idx]]


def pad_collate_fn(insts):
    """
    Pad the instance to the max seq length in batch
    """
    insts, golds = list(zip(*insts))
    max_len = max(len(gold) for gold in golds)

    golds = torch.tensor([gold + [Constants.actionPadId] * (max_len - len(gold)) for gold in golds], dtype=torch.long)
    return [insts, golds]


def load_data(config):
    data = torch.load(config.data_path)
    train_dataset = CWSBertDataset(data['train_insts'], data['train_golds'])
    train_data = DataLoader(dataset=train_dataset, batch_size=config.batch_size, shuffle=config.shuffle,
                            num_workers=config.num_workers, collate_fn=pad_collate_fn, drop_last=config.drop_last)
    dev_data = DataLoader(dataset=CWSBertDataset(data['dev_insts'], data['dev_golds']), batch_size=config.batch_size,
                          shuffle=config.shuffle, num_workers=config.num_workers, collate_fn=pad_collate_fn,
                          drop_last=config.drop_last)
    test_data = DataLoader(dataset=CWSBertDataset(data['test_insts'], data['test_golds']), batch_size=config.batch_size,
                           shuffle=config.shuffle, num_workers=config.num_workers, collate_fn=pad_collate_fn,
                           drop_last=config.drop_last)
    print('train_dataset, dev_dataset, test_dataset loading completes.')
    return train_data, dev_data, test_data, train_dataset